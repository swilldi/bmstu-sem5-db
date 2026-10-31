# JSON в PostgreSQL (лабораторная 5)

Материал к лабораторной 5 «Использование XML/JSON с базами данных». Все примеры на схеме автогонок из лабы 1: `driver`, `car`, `team`, `track`, `race_entry`, `contract`. База `study` из `docker-compose.yml` (контейнер `study-pg`, порт 5433).

В конце ты сможешь:
- выгрузить любую таблицу или связку таблиц в JSON-файл;
- загрузить JSON-файл обратно в таблицу и доказать, что она совпадает с исходной;
- хранить в таблице столбец `jsonb` и работать с ним: доставать фрагменты и значения, проверять наличие ключей, изменять документ, разворачивать его в строки.

Как проходить: по порядку, весь код набирать руками в `psql`, после каждого урока делать практику. Примеры идут на `track` и `car`, практика на `driver`, `team`, `race_entry`, чтобы ты применял, а не копировал.

**Что нужно знать заранее.** Только SQL из лаб 1–4 (SELECT, JOIN, подзапросы, агрегаты, UPDATE). Больших отдельных разделов эта лаба не требует.

**Содержание**

- Часть I. Основы
  - [Урок 0. Подготовка](#урок-0-подготовка)
  - [Урок 1. json и jsonb](#урок-1-json-и-jsonb)
  - [Урок 2. Строка таблицы в JSON](#урок-2-строка-таблицы-в-json)
  - [Урок 3. Сборка документа: массивы и вложенность](#урок-3-сборка-документа-массивы-и-вложенность)
- Часть II. Файлы
  - [Урок 4. Выгрузка JSON в файл](#урок-4-выгрузка-json-в-файл)
  - [Урок 5. Загрузка JSON из файла в таблицу](#урок-5-загрузка-json-из-файла-в-таблицу)
- Часть III. Столбец jsonb
  - [Урок 6. Добавляем столбец jsonb и заполняем его](#урок-6-добавляем-столбец-jsonb-и-заполняем-его)
  - [Урок 7. Извлечение фрагментов и значений](#урок-7-извлечение-фрагментов-и-значений)
  - [Урок 8. Проверка существования ключа](#урок-8-проверка-существования-ключа)
  - [Урок 9. Изменение документа](#урок-9-изменение-документа)
  - [Урок 10. Разбиение документа на строки](#урок-10-разбиение-документа-на-строки)
  - [Урок 11. Индексы для jsonb](#урок-11-индексы-для-jsonb)
- [Итог: скрипт лабораторной](#итог-скрипт-лабораторной)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. Основы

## Урок 0. Подготовка

Проверим, что база поднята и данные на месте.

```bash
docker compose up -d                                    # в папке с docker-compose.yml
psql -h localhost -p 5433 -U postgres -d study          # пароль postgres
```

Подключайся с **хоста** (`psql` на твоём компьютере), а не через `docker exec`. Причина в уроке 4: файлы, которые выгружает `psql`, создаются там, где он запущен, а внутри контейнера рабочая папка `/workspace` смонтирована только для чтения.

```sql
SELECT version();

SELECT 'driver' AS t, count(*) FROM driver
UNION ALL SELECT 'car', count(*) FROM car
UNION ALL SELECT 'team', count(*) FROM team
UNION ALL SELECT 'track', count(*) FROM track
UNION ALL SELECT 'race_entry', count(*) FROM race_entry
UNION ALL SELECT 'contract', count(*) FROM contract;
```

Ожидаемо примерно 6 тысяч пилотов, 7,5 тысячи машин и 54 тысячи заездов.

У тебя PostgreSQL 17 (`FROM postgres:17` в `dockerfile`), поэтому доступны и SQL/JSON-функции `JSON_TABLE`, `JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`. В уроках они идут вторым вариантом рядом с классическими.

### Практика

1. Проверь версию сервера и количество строк. Если таблицы пустые, пересоздай том: `docker compose down -v && docker compose up -d` (скрипты из `initdb` выполнятся заново).

## Урок 1. json и jsonb

В PostgreSQL два JSON-типа. Разберёмся в разнице, чтобы дальше осознанно выбирать `jsonb`.

```sql
SELECT '{"b": 1, "a": 2, "a": 3}'::json  AS as_json,
       '{"b": 1, "a": 2, "a": 3}'::jsonb AS as_jsonb;
```

```
         as_json          |     as_jsonb
--------------------------+------------------
 {"b": 1, "a": 2, "a": 3} | {"a": 3, "b": 1}
```

| | `json` | `jsonb` |
|---|---|---|
| Хранение | текст как есть | разобранное бинарное дерево |
| Порядок ключей, пробелы | сохраняются | не сохраняются |
| Дубли ключей | остаются | побеждает последний |
| Операторы `?`, `@>`, `jsonb_set` | нет | есть |
| GIN-индексы | нет | есть |
| Запись | чуть быстрее | чуть медленнее (разбор) |
| Чтение и поиск | медленнее | быстрее |

Для хранения и запросов почти всегда `jsonb`. `json` нужен, только если важно сохранить исходный текст байт в байт.

```sql
SELECT '42'::jsonb, '"Монца"'::jsonb, 'true'::jsonb, 'null'::jsonb, '[1, 2, 3]'::jsonb;
SELECT jsonb_typeof('[1,2]'), jsonb_typeof('{"a":1}'), jsonb_typeof('"x"');
```

> SQL-`NULL` и JSON-`null` разные вещи. `'null'::jsonb IS NULL` вернёт `false`: это непустое значение типа `jsonb`, внутри которого лежит JSON-null.

> Ключи и строки в JSON только в двойных кавычках. `'{name: "x"}'::jsonb` выдаст ошибку синтаксиса.

### Практика

1. Сделай `jsonb`-литерал, описывающий одну гонку (трасса объектом, массив из трёх финишировавших пилотов с позицией и временем) и проверь `jsonb_typeof` верхнего уровня и массива.
2. Сломай литерал (одинарные кавычки, лишняя запятая) и прочитай ошибку: она показывает символ, на котором упал разбор.

## Урок 2. Строка таблицы в JSON

Самый короткий путь из таблицы в JSON: превратить строку целиком в объект.

```sql
SELECT to_jsonb(t) FROM track t LIMIT 2;
```

```
{"name": "Indianapolis Motor Speedway", "country": "United States", "track_id": 1, "length_km": 4.22, "track_type": "oval", "opened_year": 1909}
```

`to_jsonb(t)` берёт алиас таблицы как значение «строка `track`» и делает из него объект: имена столбцов становятся ключами.

`row_to_json(t)` — то же, но тип `json` и порядок ключей как в таблице.

Объект с выбранными ключами:

```sql
SELECT jsonb_build_object(
         'id',     t.track_id,
         'name',   t.name,
         'km',     t.length_km,
         'type',   t.track_type,
         'since',  t.opened_year
       ) AS doc
FROM track t
ORDER BY t.track_id
LIMIT 5;
```

Аргументы парами: ключ, значение, ключ, значение…

Как типы SQL переходят в JSON, включая твой особенный `interval`:

| SQL | JSON |
|---|---|
| `int`, `smallint`, `numeric` | число |
| `text` | строка |
| `boolean` (`team.is_active`) | `true`/`false` |
| `NULL` | `null` |
| `date` (`race_date`) | строка `"1950-05-13"` |
| `interval` (`best_lap`, `total_time`) | строка `"00:01:51.792"` |

Посмотри своими глазами:

```sql
SELECT to_jsonb(re) FROM race_entry re LIMIT 2;
```

> `interval` в JSON — строка, а не число. Сравнивать её с другой строкой можно (формат фиксированный), а считать — нет: для арифметики нужно привести обратно `(... ->> 'best_lap')::interval` или заранее положить в документ секунды: `extract(epoch FROM best_lap)`.

> `jsonb_build_object` с нечётным числом аргументов падает. Если ошибка непонятная, пересчитай аргументы.

Подробнее: [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html), раздел «JSON Creation Functions».

### Практика

1. Выведи пилотов объектами с ключами `id`, `name`, `born`, `license`, `country`.
2. Выведи заезд объектом, где лучший круг лежит и строкой (`best_lap`), и числом секунд (`best_lap_s`).

## Урок 3. Сборка документа: массивы и вложенность

Одна строка = один объект. Теперь вся таблица в массив и вложенные документы.

```sql
SELECT jsonb_agg(to_jsonb(t) ORDER BY t.track_id) AS tracks FROM track t;
```

`jsonb_agg` — агрегат, склеивающий значения в JSON-массив. `ORDER BY` внутри задаёт порядок элементов.

Гонка с протоколом: трасса и дата наверху, внутри массив результатов по местам.

```sql
SELECT jsonb_pretty(jsonb_build_object(
         'track', t.name,
         'date',  re1.race_date,
         'results', (
            SELECT jsonb_agg(jsonb_build_object(
                     'pos',    re.finish_position,
                     'driver', d.full_name,
                     'car',    c.model,
                     'status', re.status,
                     'time',   re.total_time)
                   ORDER BY re.finish_position NULLS LAST, re.grid_position)
            FROM race_entry re
            JOIN driver d ON d.driver_id = re.driver_id
            JOIN car c    ON c.car_id    = re.car_id
            WHERE re.track_id = re1.track_id AND re.race_date = re1.race_date)))
FROM (SELECT DISTINCT track_id, race_date FROM race_entry
      ORDER BY race_date DESC LIMIT 1) re1
JOIN track t ON t.track_id = re1.track_id;
```

> Гонку у тебя определяет пара `(track_id, race_date)`, а не одна дата: в один день бывает несколько гонок на разных трассах (в данных таких дат больше пятисот). Соединение только по дате склеило бы чужие результаты.

Три уровня: команда → машины → заезды на них:

```sql
SELECT jsonb_pretty(jsonb_agg(
  jsonb_build_object(
    'team', tm.name,
    'cars', (
      SELECT coalesce(jsonb_agg(jsonb_build_object(
               'model',  c.model,
               'season', c.season_year,
               'starts', (SELECT count(*) FROM race_entry re WHERE re.car_id = c.car_id),
               'wins',   (SELECT count(*) FROM race_entry re WHERE re.car_id = c.car_id AND re.finish_position = 1)
             ) ORDER BY c.season_year), '[]')
      FROM car c WHERE c.team_id = tm.team_id))))
FROM team tm
WHERE tm.name IN ('Ferrari', 'McLaren');
```

> Без `coalesce(..., '[]')` у команды без машин будет `"cars": null`, а не пустой массив: агрегат над нулём строк возвращает `NULL`.

`jsonb_pretty` только форматирует вывод.

Вариант через `GROUP BY`:

```sql
SELECT tm.name,
       jsonb_agg(c.model ORDER BY c.season_year) FILTER (WHERE c.car_id IS NOT NULL) AS cars
FROM team tm
LEFT JOIN car c ON c.team_id = tm.team_id
GROUP BY tm.team_id, tm.name
LIMIT 10;
```

> `FILTER (WHERE ...)` нужен из-за `LEFT JOIN`: у команды без машин будет строка с `c.* = NULL`, и без фильтра в массив попадёт `[null]`.

### Практика

1. Собери документ «пилот → контракты (команда, начало, конец) → для каждого контракта число гонок пилота в этот период». Открытый контракт (`end_date IS NULL`) считай до сегодняшнего дня.
2. (*) Собери дерево команд (`team_parent_id`) на два уровня: родитель → массив дочерних команд с их странами. У команды без детей должно быть `[]`.

# Часть II. Файлы

## Урок 4. Выгрузка JSON в файл

Пункт 1 лабы: сохранить JSON в файл на своём компьютере.

```sql
\t on
\a
\o track.json
SELECT jsonb_pretty(jsonb_agg(to_jsonb(t) ORDER BY t.track_id)) FROM track t;
\o
\a
\t off
```

| Команда | Что делает |
|---|---|
| `\t on` | только строки, без заголовка и «(1 row)» |
| `\a` | невыровненный вывод |
| `\o файл` | писать вывод в файл |
| `\o` | вернуть вывод на экран |

Файл появится в каталоге, откуда запущен `psql`.

```bash
head track.json
```

Одной командой из терминала:

```bash
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d study -At \
  -c "SELECT jsonb_agg(to_jsonb(t) ORDER BY track_id) FROM track t" > track.json
```

> **Особенность твоего стенда.** Если запустить `psql` внутри контейнера (`docker exec -it study-pg psql`), текущая папка там — `/workspace`, а она смонтирована как `./:/workspace:ro`, только для чтения. `\o track.json` упадёт с `Read-only file system`. Либо запускай `psql` на хосте (как выше), либо пиши в `/tmp` контейнера и забирай файл: `docker cp study-pg:/tmp/track.json .`.

> Не выгружай JSON через `COPY ... TO` в текстовом формате: `COPY` экранирует обратные слэши и переводы строк, и файл перестанет быть валидным JSON. Через `\o` или `-At` текст выходит как есть.

> `COPY ... TO '/путь'` (без обратного слэша) пишет файл на машине **сервера**, то есть внутри контейнера.

Подробнее: [psql](https://www.postgresql.org/docs/current/app-psql.html), команды `\o`, `\t`, `\a`.

### Практика

1. Выгрузи в `race_entry_2025.json` все заезды 2025 года одним массивом, отсортированным по дате и трассе.
2. Выгрузи протокол гонки из урока 3 в `race.json` и открой его в редакторе.

## Урок 5. Загрузка JSON из файла в таблицу

Пункт 2 лабы: загрузить файл обратно и получить таблицу, совпадающую с исходной.

### Шаг 1. Таблица-копия той же структуры

```sql
DROP TABLE IF EXISTS track_copy;
CREATE TABLE track_copy (LIKE track INCLUDING ALL);
```

`LIKE ... INCLUDING ALL` копирует столбцы, `NOT NULL`, `CHECK` (твои `chk_length_km`, `chk_track_type`, `chk_opened_year`), значения по умолчанию и индексы, включая первичный ключ и `UNIQUE (name, country)`. Внешние ключи **не копируются**.

Ограничения у тебя добавлены отдельным файлом через `ALTER TABLE`, но для `LIKE` это неважно: он копирует то, что есть у таблицы сейчас.

> С `serial` есть тонкость: `INCLUDING ALL` копирует `DEFAULT nextval('track_track_id_seq')`, то есть копия берёт номера из **той же** последовательности, что и оригинал. Для учебной копии терпимо, но знай. Независимая копия: `ALTER TABLE track_copy ALTER COLUMN track_id DROP DEFAULT` и своя последовательность.

### Шаг 2. Прочитать файл

Вариант A, клиентский: `psql` читает файл в переменную.

```sql
\set content `cat track.json`
SELECT jsonb_array_length(:'content'::jsonb);
```

`:'content'` подставляет значение переменной как строковый литерал. На Windows вместо `cat` используй `type`.

Вариант B, серверный, и у тебя он особенно удобен. Папка проекта смонтирована в контейнер как `/workspace`, поэтому сервер видит файлы проекта напрямую:

```sql
SELECT jsonb_array_length(pg_read_file('/workspace/lab-05/track.json')::jsonb);
```

(путь внутри `/workspace` тот же, что у файла относительно папки с `docker-compose.yml`)

> `pg_read_file` требует суперпользователя или роль `pg_read_server_files`. Ты подключаешься как `postgres`, это суперпользователь, так что работает.

Сохраним документ как есть (часть задания «загрузка и сохранение JSON-файла в таблицу»):

```sql
CREATE TABLE IF NOT EXISTS json_import (
    id         serial PRIMARY KEY,
    file_name  text        NOT NULL,
    loaded_at  timestamptz NOT NULL DEFAULT now(),
    doc        jsonb       NOT NULL
);

INSERT INTO json_import (file_name, doc) VALUES ('track.json', :'content'::jsonb);
```

### Шаг 3. Развернуть массив в строки

```sql
INSERT INTO track_copy
SELECT * FROM jsonb_populate_recordset(NULL::track,
         (SELECT doc FROM json_import WHERE file_name = 'track.json'
          ORDER BY id DESC LIMIT 1));
```

`jsonb_populate_recordset(NULL::track, doc)` превращает каждый объект массива в строку типа `track`, сопоставляя ключи со столбцами.

Явный id у `serial` вставлять можно, но последовательность не сдвигается. Если у копии своя последовательность, сдвинь её:

```sql
SELECT setval(pg_get_serial_sequence('track_copy', 'track_id'), (SELECT max(track_id) FROM track_copy));
```

(если копия делит последовательность с оригиналом, `pg_get_serial_sequence` вернёт `NULL`, и делать ничего не нужно)

### Шаг 4. Доказать совпадение

```sql
(SELECT * FROM track      EXCEPT SELECT * FROM track_copy)
UNION ALL
(SELECT * FROM track_copy EXCEPT SELECT * FROM track);
```

Ноль строк — совпадают. В обе стороны, иначе не увидишь лишних строк в копии.

Структура:

```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns WHERE table_name = 'track'
EXCEPT
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns WHERE table_name = 'track_copy';
```

> Не загружай прямо в исходные таблицы: внешние ключи у тебя без `ON DELETE`, то есть `NO ACTION`. `DELETE FROM track` упадёт, пока на трассы ссылаются заезды. Это хорошо, база защищает данные. Поэтому загружаем в копию.

Если ключи в файле называются иначе — `jsonb_to_recordset` с явными столбцами:

```sql
SELECT r.id AS track_id, r.title AS name
FROM jsonb_to_recordset('[{"id": 1, "title": "Monza"}]') AS r(id int, title text);
```

Подробнее: [JSON Processing Functions](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-JSON-PROCESSING).

### Практика

1. Проделай весь цикл для `driver`: файл → `json_import` → `driver_copy` → сравнение в обе стороны 0 строк.
2. Испорти файл: поставь одному пилоту `"license_class": "F"`. Какая ошибка и откуда она взялась (вспомни, что копирует `INCLUDING ALL`)?
3. (*) Сделай круг для `race_entry` за один год: составной первичный ключ и два `interval`. Убедись, что `best_lap` и `total_time` после круга «interval → строка → interval» не изменились (сравнение `EXCEPT` это и проверит).

# Часть III. Столбец jsonb

## Урок 6. Добавляем столбец jsonb и заполняем его

Пункт 3 лабы: атрибут с типом JSON. Добавим машинам технические характеристики: у формулы, гиперкара и стоковой машины они совсем разные, раскладывать по столбцам неудобно. Типичный случай для `jsonb`.

```sql
ALTER TABLE car ADD COLUMN specs jsonb;
```

Заполняем через `UPDATE` (подставь свои `car_id`):

```sql
UPDATE car SET specs = '{
  "engine": {"layout": "V6", "turbo": true, "displacement_l": 1.6, "hybrid": {"ers_kw": 120}},
  "aero":   {"drs": true, "downforce": "high"},
  "tyres":  ["soft", "medium", "hard", "intermediate", "wet"],
  "sponsors": [
    {"name": "Petronas", "share": 0.35},
    {"name": "INEOS",    "share": 0.20}
  ],
  "homologated": true
}' WHERE car_id = 1;

UPDATE car SET specs = '{
  "engine": {"layout": "V8", "turbo": false, "displacement_l": 5.8},
  "tyres":  ["slick"],
  "homologated": true
}' WHERE car_id = 2;
```

Документы специально разные: у второй машины нет `aero` и `sponsors`. Это понадобится в уроке 8.

Генерация правдоподобных данных для всех машин из существующих столбцов:

```sql
UPDATE car c SET specs = jsonb_build_object(
  'engine', jsonb_build_object(
      'layout', CASE WHEN c.horsepower > 900 THEN 'V6 hybrid'
                     WHEN c.horsepower > 600 THEN 'V8'
                     ELSE 'I4' END,
      'turbo',  c.season_year >= 1977 AND c.car_class IN ('formula', 'hypercar')),
  'power_to_weight', round(c.horsepower / c.weight_kg, 3),
  'tyres', CASE c.car_class
             WHEN 'formula' THEN '["soft","medium","hard"]'::jsonb
             WHEN 'stock'   THEN '["slick"]'::jsonb
             ELSE '["dry","wet"]'::jsonb END,
  'homologated', true)
  || CASE WHEN c.car_class = 'formula' AND c.season_year >= 2011
          THEN jsonb_build_object('aero', jsonb_build_object('drs', true))
          ELSE '{}'::jsonb END
WHERE c.specs IS NULL;
```

`||` склеивает объекты: у современных формул появится ключ `aero`, у остальных нет.

> Чтобы в столбце был именно объект, добавь `CHECK (specs IS NULL OR jsonb_typeof(specs) = 'object')`. Без проверок туда можно положить хоть число `5`.

> Если у тебя включён триггер аудита из лабы 3 (`tr_race_entry_audit`), он висит на `race_entry`, а не на `car`, так что этот `UPDATE` его не затронет. Но в практике ниже, где меняется `race_entry`, каждое изменение запишется ещё и в `race_entry_audit`.

### Практика

1. Добавь в `race_entry` столбец `pit_stops jsonb`: массив объектов `{"lap": ..., "duration_s": ..., "tyre": ...}`. Заполни заезды одной гонки правдоподобными пит-стопами. Количество стопов 1–3, круг не больше `laps_completed`, у `dns` массив пустой.
2. (*) Заполни `pit_stops` одним `UPDATE` для всех финишировавших заездов 2025 года.

<details><summary>Подсказка</summary>

Массив можно собрать подзапросом: `(SELECT jsonb_agg(jsonb_build_object('lap', 1 + floor(random() * laps_completed)::int, ...)) FROM generate_series(1, 1 + floor(random() * 3)::int))`. Так как подзапрос ссылается на `laps_completed` текущей строки, он вычисляется для каждой строки заново.

</details>

## Урок 7. Извлечение фрагментов и значений

Пункты 4.1 и 4.2: достать кусок JSON и конкретные значения. Одни операторы возвращают `jsonb`, другие `text`.

```sql
SELECT model,
       specs -> 'engine'                AS engine_json,     -- jsonb-фрагмент
       specs -> 'engine' ->> 'layout'   AS layout,          -- text
       specs #> '{engine,hybrid}'       AS hybrid_json,     -- jsonb по пути
       specs #>> '{engine,hybrid,ers_kw}' AS ers_kw_text,   -- text по пути
       specs -> 'tyres' -> 0            AS first_tyre,      -- элемент массива (с 0)
       specs #>> '{sponsors,0,name}'    AS title_sponsor
FROM car
WHERE specs IS NOT NULL
LIMIT 20;
```

| Оператор | Пример | Возвращает |
|---|---|---|
| `->` ключ | `specs -> 'engine'` | `jsonb` |
| `->` индекс | `specs -> 'tyres' -> 0` | `jsonb` |
| `->>` | `specs ->> 'power_to_weight'` | `text` |
| `#>` путь | `specs #> '{engine,layout}'` | `jsonb` |
| `#>>` путь | `specs #>> '{sponsors,0,name}'` | `text` |

Приведение типов для сравнений:

```sql
SELECT model, season_year, (specs ->> 'power_to_weight')::numeric AS pw
FROM car
WHERE (specs #>> '{engine,turbo}')::boolean
ORDER BY pw DESC
LIMIT 10;
```

> `specs -> 'power_to_weight' > 1` выдаст ошибку: слева `jsonb`, справа число. Бери `->>` и приводи.

> `->` и `->>` по несуществующему ключу дают `NULL`, без ошибки. Опечатка в ключе тихо даёт пустой результат.

JSONPath:

```sql
-- спонсоры с долей больше 30%, каждый отдельной строкой
SELECT model, jsonb_path_query(specs, '$.sponsors[*] ? (@.share > 0.3)') FROM car;

-- имена всех спонсоров одним массивом
SELECT model, jsonb_path_query_array(specs, '$.sponsors[*].name') FROM car WHERE specs ? 'sponsors';

SELECT model, jsonb_path_query_first(specs, '$.engine.displacement_l') FROM car WHERE car_id <= 5;
```

`$` — корень, `[*]` — все элементы, `? (...)` — фильтр, `@` — текущий элемент.

PostgreSQL 17:

```sql
SELECT model,
       JSON_VALUE(specs, '$.engine.layout')                      AS layout,
       JSON_VALUE(specs, '$.power_to_weight' RETURNING numeric)  AS pw,
       JSON_QUERY(specs, '$.tyres')                              AS tyres
FROM car
LIMIT 10;
```

Подробнее: [SQL/JSON Path Language](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-SQLJSON-PATH).

### Практика

1. Из `race_entry.pit_stops` выведи пилота, дату и длительность первого пит-стопа.
2. Выведи заезды, где хоть один пит-стоп длился больше 5 секунд (через JSONPath).
3. (*) Посчитай для каждого заезда суммарное время на пит-стопах и сравни с `total_time`: какую долю гонки пилот простоял?

## Урок 8. Проверка существования ключа

Пункт 4.3. Операторы «есть ли ключ» и «содержит ли фрагмент».

```sql
SELECT model,
       specs ? 'aero'                          AS has_aero,
       specs ?| ARRAY['aero', 'sponsors']      AS has_any,
       specs ?& ARRAY['engine', 'tyres']       AS has_all,
       specs -> 'engine' ? 'hybrid'            AS is_hybrid,
       specs -> 'tyres' ? 'wet'                AS has_wet     -- для массива строк ? ищет элемент
FROM car
LIMIT 20;
```

`@>` — «содержит фрагмент»:

```sql
SELECT count(*) FROM car WHERE specs @> '{"engine": {"turbo": true}}';
SELECT model FROM car WHERE specs @> '{"aero": {"drs": true}}' LIMIT 10;
SELECT model FROM car WHERE specs @> '{"sponsors": [{"name": "Petronas"}]}';
```

JSONPath для условий:

```sql
SELECT model FROM car WHERE specs @? '$.engine ? (@.displacement_l < 2)';
SELECT model FROM car WHERE jsonb_path_exists(specs, '$.sponsors[*] ? (@.share >= 0.2)');
```

PostgreSQL 17: `JSON_EXISTS(specs, '$.aero')`.

> `?` проверяет только ключи верхнего уровня (или строки-элементы массива). `specs ? 'turbo'` вернёт `false`, хотя ключ есть в `engine`. Для вложенных: `specs -> 'engine' ? 'turbo'` или JSONPath.

> В драйверах (JDBC, иногда psycopg) `?` может приниматься за параметр. Из приложения (лаба 6) удобнее `jsonb_exists(specs, 'aero')` или JSONPath.

| Задача | Способ |
|---|---|
| есть ключ наверху | `doc ? 'k'` |
| ключ во вложенном объекте | `doc -> 'a' ? 'k'` или `doc @? '$.a.k'` |
| значение равно X | `doc @> '{"k": X}'` |
| элемент массива с условием | `doc @? '$.arr[*] ? (@.x > 1)'` |

### Практика

1. Найди финишировавшие заезды без пит-стопов: ключа нет (`pit_stops IS NULL`) или массив пустой. Выведи эти случаи отдельной колонкой.
2. Найди заезды, где ставили дождевые шины (`"tyre": "wet"`), двумя способами: `@>` и JSONPath.

## Урок 9. Изменение документа

Пункт 4.4. `jsonb` неизменяем: функции возвращают новый документ, который записываешь через `UPDATE`.

```sql
-- заменить значение по пути
UPDATE car SET specs = jsonb_set(specs, '{engine,hybrid,ers_kw}', '160') WHERE car_id = 1;

-- добавить ключ (создаётся последний ключ пути)
UPDATE car SET specs = jsonb_set(specs, '{aero}', '{"drs": false, "downforce": "low"}') WHERE car_id = 2;

-- слияние верхнего уровня
UPDATE car SET specs = specs || '{"homologated": false, "note": "ожидает проверки FIA"}' WHERE car_id = 2;

-- удалить ключ
UPDATE car SET specs = specs - 'note' WHERE car_id = 2;

-- удалить по пути
UPDATE car SET specs = specs #- '{engine,hybrid}' WHERE car_id = 1;

-- добавить элемент в конец массива
UPDATE car SET specs = jsonb_insert(specs, '{sponsors,-1}', '{"name": "Aramco", "share": 0.1}', true) WHERE car_id = 1;

-- удалить элемент массива по индексу
UPDATE car SET specs = specs #- '{sponsors,0}' WHERE car_id = 1;

-- удалить строку из массива по значению
UPDATE car SET specs = jsonb_set(specs, '{tyres}', (specs -> 'tyres') - 'hard')
WHERE specs -> 'tyres' ? 'hard' AND car_id = 1;
```

> Третий аргумент `jsonb_set` — `jsonb`. Строку пиши в JSON-кавычках: `'"V10"'`, а не `'V10'`. Или `to_jsonb('V10'::text)`.

> `jsonb_set` создаёт только **последний** ключ пути. У машины без `engine.hybrid` вызов `jsonb_set(specs, '{engine,hybrid,ers_kw}', '160')` молча ничего не изменит.

> Если новое значение `NULL`, результат `jsonb_set` станет `NULL`, и `UPDATE` сотрёт документ. Для «записать null» — `'null'::jsonb`, при подстановке из столбцов — `coalesce`.

Изменение с вычислением: перераспределить доли спонсоров так, чтобы их сумма была 1:

```sql
UPDATE car c
SET specs = jsonb_set(c.specs, '{sponsors}', (
      SELECT jsonb_agg(sp || jsonb_build_object('share',
               round((sp ->> 'share')::numeric / s.total, 3)))
      FROM jsonb_array_elements(c.specs -> 'sponsors') AS sp,
           (SELECT sum((x ->> 'share')::numeric) AS total
            FROM jsonb_array_elements(c.specs -> 'sponsors') AS x) s))
WHERE c.specs ? 'sponsors';
```

Массив разбирается на элементы (урок 10), каждый меняется и собирается обратно. Сумму долей считает отдельный подзапрос `s`.

> Хочется написать `sum(...) OVER ()` прямо внутри `jsonb_agg(...)`, но PostgreSQL это запрещает: `aggregate function calls cannot contain window function calls`. Отсюда второй подзапрос.

### Практика

1. Добавь каждому финишировавшему заезду пит-стоп с шиной `"soft"` на предпоследнем круге (в конец массива `pit_stops`).
2. У одного заезда поменяй длительность второго пит-стопа и удали третий.
3. Добавь пит-стоп заезду, у которого `pit_stops` был `NULL`. Что вернёт `jsonb_set(NULL, ...)` или `jsonb_insert(NULL, ...)`, и как это обойти?

## Урок 10. Разбиение документа на строки

Пункт 4.5: массив или объект внутри документа → обычные строки.

Массив объектов → строки:

```sql
SELECT c.model, sp ->> 'name' AS sponsor, (sp ->> 'share')::numeric AS share
FROM car c
CROSS JOIN LATERAL jsonb_array_elements(c.specs -> 'sponsors') AS sp;
```

`LATERAL` даёт функции справа доступ к строке слева. Машины без спонсоров выпадут; если они нужны: `LEFT JOIN LATERAL ... ON true`.

Массив строк → строки:

```sql
SELECT c.model, tyre
FROM car c, jsonb_array_elements_text(c.specs -> 'tyres') AS tyre
WHERE c.car_id <= 5;
```

Типизированные столбцы:

```sql
SELECT c.model, sp.*
FROM car c, jsonb_to_recordset(c.specs -> 'sponsors') AS sp(name text, share numeric);
```

Объект → пары:

```sql
SELECT c.model, e.key, e.value
FROM car c, jsonb_each(c.specs -> 'engine') AS e
WHERE c.car_id <= 3;
```

`JSON_TABLE` (PostgreSQL 17):

```sql
SELECT c.model, jt.*
FROM car c,
     JSON_TABLE(c.specs, '$' COLUMNS (
        layout text    PATH '$.engine.layout',
        turbo  boolean PATH '$.engine.turbo',
        pw     numeric PATH '$.power_to_weight',
        NESTED PATH '$.tyres[*]' COLUMNS (tyre text PATH '$')
     )) AS jt
WHERE c.car_id <= 5;
```

Агрегация по результату:

```sql
SELECT specs #>> '{engine,layout}' AS layout, count(*) AS cars, round(avg(horsepower)) AS avg_hp
FROM car
GROUP BY 1
ORDER BY 2 DESC;
```

### Практика

1. Выведи таблицу «дата — трасса — пилот — круг пит-стопа — шина — длительность» из `race_entry.pit_stops`.
2. Посчитай среднюю длительность пит-стопа по годам. Видно ли, что стопы становятся быстрее?
3. (*) Сделай п.1 через `JSON_TABLE`.

## Урок 11. Индексы для jsonb

Необязательно, но полезно на защите: показывает, зачем `jsonb`, а не `text`. У тебя 7,5 тысячи машин и 54 тысячи заездов, на них эффект индекса уже виден.

```sql
CREATE INDEX idx_car_specs ON car USING gin (specs);
```

GIN ускоряет `@>`, `?`, `?|`, `?&`, `@?`. Для одного часто используемого поля — B-tree по выражению:

```sql
CREATE INDEX idx_car_layout ON car ((specs #>> '{engine,layout}'));
```

Проверка:

```sql
EXPLAIN ANALYZE SELECT model FROM car WHERE specs @> '{"engine": {"turbo": true}}';
```

Ищи в плане `Bitmap Index Scan on idx_car_specs`. Если планировщик всё равно выбрал `Seq Scan` (так бывает, когда условию подходит большая часть таблицы), проверь на редком значении: `specs @> '{"sponsors": [{"name": "Petronas"}]}'`.

### Практика

1. Создай GIN-индекс на `race_entry.pit_stops` и сравни `EXPLAIN ANALYZE` запроса с `@>` до и после.

---

# Итог: скрипт лабораторной

Сдавать удобно одним `lab05.sql`, разделённым по пунктам:

```sql
-- ===== 1. Выгрузка в JSON =====
SELECT to_jsonb(t) FROM track t;
SELECT jsonb_agg(to_jsonb(t) ORDER BY track_id) FROM track t;
-- вложенный: гонка → результаты (урок 3)
-- в файл: \t on \a \o track.json ... \o   (psql на хосте!)

-- ===== 2. Загрузка из файла =====
\set content `cat track.json`
INSERT INTO json_import (file_name, doc) VALUES ('track.json', :'content'::jsonb);
CREATE TABLE track_copy (LIKE track INCLUDING ALL);
INSERT INTO track_copy
SELECT * FROM jsonb_populate_recordset(NULL::track, :'content'::jsonb);
-- проверка: EXCEPT в обе стороны = 0 строк

-- ===== 3. Столбец jsonb =====
ALTER TABLE car ADD COLUMN specs jsonb;
-- UPDATE из урока 6

-- ===== 4. Работа с документом =====
-- 4.1 фрагмент:       specs -> 'engine', JSON_QUERY
-- 4.2 значения:       specs #>> '{engine,layout}', jsonb_path_query, JSON_VALUE
-- 4.3 существование:  ?, ?|, ?&, @>, @?, JSON_EXISTS
-- 4.4 изменение:      jsonb_set, ||, -, #-, jsonb_insert
-- 4.5 разбиение:      jsonb_array_elements, jsonb_to_recordset, JSON_TABLE
```

Запуск с хоста: `PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d study -f lab05.sql`. `\set` и `\o` работают только в `psql`.

> Если положить `lab05.sql` в папку проекта, внутри контейнера он будет виден как `/workspace/lab-05/lab05.sql` и его можно запустить `docker exec study-pg psql -f /workspace/lab-05/lab05.sql`. Но выгрузка через `\o` там не сработает (только чтение), поэтому выгрузку делай с хоста.

# Финальное задание

Пройди лабу заново на других таблицах, не подглядывая в уроки:

- Выгрузи в файл документ «трасса → гонки на ней (дата) → победитель, поул (`grid_position = 1`) и число сошедших» для пяти самых используемых трасс.
- Выгрузи `contract` в файл и загрузи в `contract_copy` (составной ключ `(driver_id, start_date)`, `end_date` с `NULL` у открытых контрактов); докажи совпадение данных и структуры.
- Добавь в `team` столбец `profile jsonb`: штаб-квартира (объект с городом и страной), руководители (массив объектов с должностью и годами), титулы (массив годов). Заполни все команды одним `UPDATE`, титулы посчитай по данным: годы, в которые пилот команды выиграл больше всех гонок.
- Напиши по два запроса на каждый подпункт 4.1–4.5 для `profile`, в том числе:
  - команды с хотя бы одним титулом после 2000 года;
  - добавление нового руководителя всем активным командам;
  - таблица «команда — год титула» с сортировкой.
- Создай подходящий индекс и покажи план запроса.

# Шпаргалка

```sql
-- создание
to_jsonb(row)  row_to_json(row)  jsonb_build_object('k', v, ...)  jsonb_build_array(...)
jsonb_agg(x ORDER BY ...)  jsonb_object_agg(k, v)  jsonb_pretty(doc)
extract(epoch FROM interval_col)   -- interval в секунды для JSON-числа

-- чтение
doc -> 'k'   doc -> 0   doc ->> 'k'   doc #> '{a,b}'   doc #>> '{a,0,b}'
jsonb_path_query(doc, '$.arr[*] ? (@.x > 1)')   jsonb_path_query_first   jsonb_path_query_array
JSON_VALUE(doc, '$.a' RETURNING numeric)   JSON_QUERY(doc, '$.arr')

-- проверки
doc ? 'k'   doc ?| ARRAY['a','b']   doc ?& ARRAY['a','b']   doc @> '{"k": 1}'
doc @? '$.a ? (@ > 1)'   jsonb_path_exists(doc, '$.a')   JSON_EXISTS(doc, '$.a')

-- изменение
jsonb_set(doc, '{a,b}', '"значение"')   jsonb_insert(doc, '{arr,-1}', '{...}', true)
doc || '{"k": 1}'   doc - 'k'   doc - 0   doc #- '{a,b}'

-- разбиение
jsonb_array_elements(arr)   jsonb_array_elements_text(arr)   jsonb_each(obj)   jsonb_object_keys(obj)
jsonb_to_recordset(arr) AS t(a int, b text)   jsonb_populate_recordset(NULL::table, arr)
JSON_TABLE(doc, '$.arr[*]' COLUMNS (a int PATH '$.a'))

-- файлы (psql на хосте, порт 5433)
\t on  \a  \o file.json  SELECT ...;  \o
\set content `cat file.json`   SELECT :'content'::jsonb;
pg_read_file('/workspace/путь/file.json')::jsonb      -- серверное чтение из папки проекта
SELECT setval(pg_get_serial_sequence('t','id'), (SELECT max(id) FROM t));
```

# Источники и что почитать дальше

**Официальная документация**
- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) — разница `json`/`jsonb`, вложение `@>`, индексы.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html) — все операторы, функции и JSONPath; главный справочник к лабе.
- [psql](https://www.postgresql.org/docs/current/app-psql.html) — `\o`, `\set`, `\copy` и подстановка переменных.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html) — почему текстовый формат экранирует данные и чем `COPY` отличается от `\copy`.
- [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html) — `pg_read_file` и права на чтение серверных файлов.
