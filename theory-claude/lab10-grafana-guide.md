# Дашборды в Grafana (лабораторная 10)

Материал к лабораторной 10 «BI инструменты для визуализации данных». Ставим Grafana, подключаем к ней базу автогонок из лабы 1 (`study` в контейнере `study-pg`, порт 5433) и собираем дашборд «Гонки» из 6 панелей: таблица, график по времени, столбчатая диаграмма, крупное число, круговая диаграмма и шкала. Панели фильтруются переменными (тип трассы, команда).

В конце ты сможешь:
- поднять Grafana в Docker и подключить PostgreSQL;
- писать SQL-запросы для разных типов панелей и понимать, чего каждая ждёт на входе;
- использовать макросы времени и переменные дашборда;
- сохранить дашборд в JSON и восстановить его.

Как проходить: по порядку. Запросы сначала проверяй в `psql`, потом вставляй в панель. Каждый урок добавляет на дашборд одну-две панели.

**Что нужно знать заранее**

- **Docker и Docker Compose** (большой раздел, по ходу не объясняется): `docker compose up -d`, порты, тома. Если слабо, сначала [Docker: Get started](https://docs.docker.com/get-started/).
- **SQL из лаб 1–4**: `GROUP BY`, `JOIN`, `date_trunc`.

**Содержание**

- Часть I. Подготовка
  - [Урок 0. Как устроена Grafana](#урок-0-как-устроена-grafana)
  - [Урок 1. Grafana в Docker](#урок-1-grafana-в-docker)
  - [Урок 2. Пользователь только для чтения](#урок-2-пользователь-только-для-чтения)
  - [Урок 3. Источник данных PostgreSQL](#урок-3-источник-данных-postgresql)
  - [Урок 4. Данные и время](#урок-4-данные-и-время)
- Часть II. Панели
  - [Урок 5. Таблица](#урок-5-таблица)
  - [Урок 6. График по времени](#урок-6-график-по-времени)
  - [Урок 7. Столбчатая диаграмма](#урок-7-столбчатая-диаграмма)
  - [Урок 8. Stat, Pie chart, Gauge](#урок-8-stat-pie-chart-gauge)
- Часть III. Дашборд целиком
  - [Урок 9. Переменные](#урок-9-переменные)
  - [Урок 10. Компоновка, сохранение, экспорт](#урок-10-компоновка-сохранение-экспорт)
  - [Урок 11. Источник данных из файла](#урок-11-источник-данных-из-файла)
- [Итог: дашборд «Гонки»](#итог-дашборд-гонки)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. Подготовка

## Урок 0. Как устроена Grafana

Grafana ничего не хранит сама: она берёт данные из источника (у нас PostgreSQL), выполняет запрос при каждом открытии дашборда или обновлении и рисует результат.

| Понятие | Что это |
|---|---|
| **Data source** | подключение к базе: адрес, пользователь, пароль |
| **Panel** | один график, таблица или число; у панели есть запрос и тип визуализации |
| **Dashboard** | набор панелей на сетке плюс общий диапазон времени и переменные |
| **Time range** | период в правом верхнем углу («Last 7 days»); панели с макросами времени показывают данные за него |
| **Variable** | выпадающий список вверху дашборда; его значение подставляется в запросы панелей |
| **Query editor** | редактор запроса у панели: **Builder** (мышкой) или **Code** (SQL руками) |

Главное, что нужно понять: **тип панели определяет, какую форму результата она ждёт**.

| Панель | Чего ждёт от запроса |
|---|---|
| Table | любые строки и столбцы |
| Time series | столбец времени `time` + числовые столбцы; строки отсортированы по времени |
| Bar chart | столбец-категория (текст) + числовые столбцы |
| Stat, Gauge | одно число (или несколько, тогда несколько плашек) |
| Pie chart | категории + значения |

Запрос, правильный для таблицы, часто не подходит для графика по времени. Большинство проблем «панель пустая» решаются проверкой формы результата.

Задание требует не менее 5 панелей, в том числе таблицу, график и столбчатую диаграмму. Сделаем 6.

### Практика

1. До работы в Grafana набросай на бумаге макет дашборда: на какие 6 вопросов о гонках он отвечает («сколько гонок за период?», «какие команды выигрывают?», «как часто сходят?», «кто приехал в последней гонке?»...) и какая панель для какого вопроса.

## Урок 1. Grafana в Docker

Пункт 1 лабы: установить Grafana. Через Docker это одна команда.

`lab10/docker-compose.yml`:

```yaml
services:
  grafana:
    image: grafana/grafana:13.2.4
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  grafana-data:
```

```bash
cd lab10
docker compose up -d
```

Открой `http://localhost:3000`, войди как `admin` / `admin`. Grafana попросит сменить пароль, это можно пропустить (Skip) на учебном стенде.

| Что | Почему так |
|---|---|
| `grafana/grafana:13.2.4` | конкретная версия: интерфейс между версиями меняется, а инструкции должны совпадать с тем, что на экране |
| том `grafana-data` | дашборды и источники хранятся во встроенной базе Grafana; без тома они пропадут при пересоздании контейнера |
| `host.docker.internal` | так контейнер Grafana достучится до порта 5433, на который проброшен `study-pg` |

> Твой PostgreSQL уже в Docker (`study-pg`) и опубликован на хост как `5433`. Официальный образ `postgres` принимает сетевые подключения с паролем, так что Grafana ходит на `host.docker.internal:5433`, как на любой порт компьютера.

> Можно добавить сервис `grafana` прямо в `docker-compose.yml` проекта рядом с `db`. Тогда адрес источника — `db:5432` (имя сервиса и внутренний порт), без проброса через хост.

> Установка без Docker тоже возможна (первый вариант в задании, [инструкция](https://grafana.com/docs/grafana/latest/setup-grafana/installation/)). Тогда адрес базы — `localhost:5433`.

### Практика

1. Подними Grafana, войди, найди в меню слева разделы **Dashboards** и **Connections**.

## Урок 2. Пользователь только для чтения

Grafana выполняет любой SQL, который написан в панели, и не проверяет, безопасен ли он. Если подключить её под `postgres`, одна панель с `DELETE` удалит данные. Поэтому создаём отдельного пользователя, которому разрешено только читать.

В `psql` под суперпользователем:

```sql
CREATE ROLE grafana_ro WITH LOGIN PASSWORD 'grafana_ro_pass';
GRANT CONNECT ON DATABASE study TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
```

| Команда | Что даёт |
|---|---|
| `GRANT CONNECT ON DATABASE` | право подключаться к базе |
| `GRANT USAGE ON SCHEMA` | право видеть объекты схемы |
| `GRANT SELECT ON ALL TABLES` | чтение **существующих** таблиц |
| `ALTER DEFAULT PRIVILEGES` | чтение таблиц, которые создадут **потом** |

Проверка (с хоста, порт 5433):

```bash
psql -h localhost -p 5433 -U grafana_ro -d study -c "SELECT count(*) FROM race_entry"
psql -h localhost -p 5433 -U grafana_ro -d study -c "DELETE FROM race_entry WHERE false"
```

Первая команда работает, вторая выдаёт `permission denied for table race_entry`.

> `GRANT SELECT ON ALL TABLES` действует только на таблицы, которые есть в момент выполнения. Без `ALTER DEFAULT PRIVILEGES` новая таблица (например, `pit_stop` из лабы 6) будет недоступна Grafana, и панель покажет `permission denied`.

> `ALTER DEFAULT PRIVILEGES` действует для таблиц, которые создаёт **тот пользователь, который выполнил команду**. Если таблицы создаёт другой пользователь, добавь `FOR ROLE имя`.

### Практика

1. Создай пользователя и проверь обе команды выше.
2. Создай новую таблицу под `postgres` и проверь, что `grafana_ro` может из неё читать. Проверь и чужие объекты из прошлых лаб: `race_entry_audit`, `pit_stop`, `json_import` — есть ли к ним доступ, и почему.

> Пользователь `grafana_ro` создаётся в базе, которая лежит в томе `pgdata`. Если пересоздашь контейнер с `docker compose down -v`, пользователь пропадёт вместе с данными. Чтобы он создавался автоматически, положи команды из урока в `initdb/05_grafana_ro.sql`.

## Урок 3. Источник данных PostgreSQL

Пункт 3 лабы: подключить базу как источник для дашборда.

1. Меню слева → **Connections** → **Add new connection**.
2. Найди **PostgreSQL**, выбери, **Add new data source**.
3. Заполни:

| Поле | Значение |
|---|---|
| Name | `StudyDB` |
| Host URL | `host.docker.internal:5433` |
| Database name | `study` |
| Username | `grafana_ro` |
| Password | `grafana_ro_pass` |
| TLS/SSL Mode | disable |
| Version | 17 (у тебя `FROM postgres:17`; «12+» из задания тоже подойдёт) |

4. **Save & test**. Должно появиться сообщение «Database Connection OK».

> В задании описан путь через «шестерёнку → Data Sources». Так было в старых версиях Grafana. Сейчас тот же раздел называется **Connections → Data sources**.

> «Host URL» — **без** `postgres://` и без имени базы, только `хост:порт`. Частая ошибка — вставить туда JDBC-строку из лабы 8.

| Ошибка при Save & test | Причина |
|---|---|
| `dial tcp ... connect: connection refused` | контейнер `study-pg` не запущен или указан порт 5432 вместо 5433 |
| `no pg_hba.conf entry for host` | PostgreSQL отклоняет подключения с этого адреса (в образе по умолчанию не встречается) |
| `password authentication failed` | неверный пароль или пользователь |
| `database "..." does not exist` | опечатка в имени базы |

Подробнее: [Configure the PostgreSQL data source](https://grafana.com/docs/grafana/latest/datasources/postgres/configure/).

### Практика

1. Подключи источник и получи «Database Connection OK».
2. Специально введи неверный пароль и посмотри на ошибку, затем исправь.

## Урок 4. Данные и время

Графикам по времени нужны данные, распределённые по периоду. У тебя с этим всё хорошо: 54 тысячи заездов с 1950 по 2026 год.

```sql
SELECT extract(year FROM race_date) AS year, count(DISTINCT (track_id, race_date)) AS races
FROM race_entry
GROUP BY 1 ORDER BY 1 DESC
LIMIT 10;
```

Главное отличие от «обычных» дашбордов: время у тебя — `date`, а не `timestamp`, и данные покрывают десятилетия. Поэтому:

| Что | Как |
|---|---|
| диапазон дашборда | не «Last 6 hours» по умолчанию, а «Last 10 years» или «Last 20 years» |
| шаг группировки | годы или месяцы, а не минуты |
| `$__timeFilter(race_date)` | работает и с `date`: PostgreSQL сравнит дату с границами диапазона |

Сразу после создания дашборда поставь диапазон: значок часов вверху справа → **Last 10 years** (или введи `now-20y` в поле From), затем **Dashboard settings → Time options** → сохрани как диапазон по умолчанию.

> Самая частая причина «пустых» панелей на этой схеме — диапазон по умолчанию «Last 6 hours». В последние 6 часов гонок нет.

### Практика

1. Найди год с наибольшим числом гонок и год с наибольшей долей сходов (`dnf`). Сохрани ответы: в уроках 6 и 8 их будет видно на графиках.

# Часть II. Панели

## Урок 5. Таблица

Первая панель — протоколы последних гонок. На ней освоим редактор панели.

1. **Dashboards** → **New** → **New dashboard** → **Add visualization** → выбери источник `StudyDB`.
2. В редакторе запроса переключись с **Builder** на **Code**.
3. Справа в списке визуализаций выбери **Table**.
4. **Format** под запросом: **Table**.

Запрос:

```sql
SELECT re.race_date                         AS "Дата",
       t.name                               AS "Трасса",
       re.finish_position                   AS "Место",
       d.full_name                          AS "Пилот",
       tm.name                              AS "Команда",
       re.grid_position                     AS "Старт",
       re.status                            AS "Статус",
       extract(epoch FROM re.best_lap)      AS "Лучший круг",
       extract(epoch FROM re.total_time)    AS "Время"
FROM race_entry re
JOIN track  t  ON t.track_id  = re.track_id
JOIN driver d  ON d.driver_id = re.driver_id
JOIN car    c  ON c.car_id    = re.car_id
JOIN team   tm ON tm.team_id  = c.team_id
WHERE $__timeFilter(re.race_date)
ORDER BY re.race_date DESC, t.name, re.finish_position NULLS LAST
LIMIT 100
```

Справа в настройках панели: **Title** = «Последние гонки». Сохрани дашборд (значок дискеты, имя «Гонки») и поставь диапазон времени, как в уроке 4.

`$__timeFilter(re.race_date)` — макрос Grafana. Перед отправкой запроса он превращается в `re.race_date BETWEEN '2016-10-20T...' AND '2026-10-20T...'` по диапазону дашборда.

**Интервалы.** `best_lap` и `total_time` имеют тип `interval`, а Grafana этот тип толком не понимает: покажет строкой или пустой ячейкой. Поэтому в запросе они переведены в секунды (`extract(epoch FROM ...)`), а показывать их красиво будет сама Grafana:

| Где | Что |
|---|---|
| Overrides → Fields with name «Лучший круг» → Standard options → Unit → Time → **Duration (hh:mm:ss)** | `00:01:14` вместо `74.26` |
| то же для «Время» | `01:32:15` |
| Overrides → «Статус» → Cell type → Colored background + Value mappings | `dnf` красным, `dsq` фиолетовым, `finished` зелёным |
| Table → Column filter | фильтр по трассе или пилоту в заголовке |

> Единицы времени в Grafana: точное название и набор форматов зависят от версии. Если «Duration (hh:mm:ss)» нет, выбери **Time → seconds (s)**: Grafana сама покажет «1.24 min».

> `LIMIT` в таблице обязателен. Без него Grafana загрузит в браузер тысячи строк, и вкладка зависнет.

> Команду берём через машину (`car.team_id`), а не через контракт: так видно, за кого пилот реально ехал в этой гонке.

> Чтобы увидеть, какой SQL Grafana реально отправила, нажми **Query inspector** → **Query**.

Подробнее: [PostgreSQL query editor](https://grafana.com/docs/grafana/latest/datasources/postgres/query-editor/).

### Практика

1. Добавь столбец «Отыграл» (`grid_position - finish_position`) и раскрась его: положительные зелёным, отрицательные красным (Thresholds или Value mappings по диапазону).
2. Посмотри в Query inspector, во что превратился `$__timeFilter`.

## Урок 6. График по времени

Панель **Time series** — заезды во времени с разбиением по статусу. Это «график» из задания.

**Add** → **Visualization** → **Time series**, **Format: Time series**.

```sql
SELECT $__timeGroupAlias(race_date, $__interval),
       count(*) AS "Заезды"
FROM race_entry
WHERE $__timeFilter(race_date)
GROUP BY 1
ORDER BY 1
```

| Макрос | Во что превращается |
|---|---|
| `$__timeFilter(col)` | `col BETWEEN <начало> AND <конец>` диапазона дашборда |
| `$__timeGroupAlias(col, '30d')` | округление времени до 30 дней с именем столбца `time` |
| `$__timeGroup(col, '30d')` | то же без алиаса (для `GROUP BY`) |
| `$__interval` | шаг, который Grafana подбирает под ширину панели и диапазон |

На диапазоне «Last 20 years» `$__interval` получится порядка нескольких дней, и график превратится в частокол отдельных гоночных уикендов. Для такой истории удобнее зафиксировать шаг: `$__timeGroupAlias(race_date, '90d')` — квартал.

Несколько линий: разбиение по статусу. Текстовый столбец Grafana делает меткой серии:

```sql
SELECT $__timeGroupAlias(race_date, '90d'),
       status   AS "Статус",
       count(*) AS "Заезды"
FROM race_entry
WHERE $__timeFilter(race_date)
GROUP BY 1, 2
ORDER BY 1
```

Включи **Graph styles → Bars** и **Stack series → Normal**: столбики кварталов, внутри доли финишей и сходов.

Вторая полезная серия — темп: средний лучший круг по кварталам. Секунды, а не `interval`:

```sql
SELECT $__timeGroupAlias(race_date, '90d'),
       avg(extract(epoch FROM best_lap)) AS "Средний лучший круг"
FROM race_entry
WHERE $__timeFilter(race_date) AND best_lap IS NOT NULL
GROUP BY 1
ORDER BY 1
```

> Для Time series обязательно `ORDER BY` по времени: без него линия рисуется «скачками».

> Если панель пишет «Data does not have a time field», проверь **Format**: должно быть Time series, а столбец времени должен называться `time` (макрос `$__timeGroupAlias` даёт это имя сам).

> Средний круг по всем трассам сразу — сомнительная величина: трассы разной длины. Честнее средняя **скорость** круга: `avg(t.length_km / extract(epoch FROM re.best_lap) * 3600)` — по сути твоя `fn_avg_speed`, только агрегатом.

### Практика

1. Сделай вторую панель Time series со средней скоростью лучшего круга по кварталам (через `JOIN track`). Видно ли, что машины стали быстрее?
2. Поставь диапазон «Last 76 years» (`now-76y`) и посмотри на всю историю. Найди год с наибольшей долей сходов из урока 4.

## Урок 7. Столбчатая диаграмма

**Bar chart** — сравнение категорий: топ-10 команд по победам за период. Это «столбовая диаграмма» из задания.

**Add** → **Visualization** → **Bar chart**, **Format: Table**.

```sql
SELECT tm.name                                          AS "Команда",
       count(*) FILTER (WHERE re.finish_position = 1)   AS "Победы",
       count(*) FILTER (WHERE re.finish_position <= 3)  AS "Подиумы"
FROM race_entry re
JOIN car  c  ON c.car_id   = re.car_id
JOIN team tm ON tm.team_id = c.team_id
WHERE $__timeFilter(re.race_date)
GROUP BY tm.team_id, tm.name
ORDER BY 2 DESC
LIMIT 10
```

Bar chart берёт первый текстовый столбец как подписи, числовые — как высоту столбцов. Два числа — два столбца на команду.

| Настройка | Значение |
|---|---|
| Orientation | Horizontal — длинные названия читаются лучше |
| Show values | Always — число на каждом столбце |
| Color scheme | Classic palette |

> **Format: Table** для Bar chart, а не Time series: здесь нет оси времени.

> Группировка по `tm.team_id`, а не по имени: у тебя `UNIQUE (name)` на `team`, так что склейки не будет, но группировать по ключу — хорошая привычка.

### Практика

1. Сделай Bar chart «Пилоты с наибольшим числом очков за период» (очки как в лабе 6: `coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[finish_position], 0)`).
2. (*) Сделай Bar chart «Сходы по трассам»: доля `dnf` на 10 трассах с наибольшим числом гонок. Какая трасса самая «злая»?

## Урок 8. Stat, Pie chart, Gauge

Три панели для одиночных значений и долей. До шести панелей на дашборде.

**Stat** — гонки и участники за период (три числа — три плашки):

```sql
SELECT count(DISTINCT (track_id, race_date))  AS "Гонок",
       count(DISTINCT driver_id)              AS "Пилотов",
       count(*)                               AS "Заездов"
FROM race_entry
WHERE $__timeFilter(race_date)
```

Format: Table, **Color mode → Background**.

**Pie chart** — заезды по статусам:

```sql
SELECT status AS "Статус", count(*) AS "Заезды"
FROM race_entry
WHERE $__timeFilter(race_date)
GROUP BY 1
ORDER BY 2 DESC
```

Format: Table. **Value options → Show → All values** (иначе Pie chart сложит все строки в один сектор), **Pie chart type → Donut**, **Legend → Values: Percent**.

**Gauge** — доля финишей среди стартовавших (`dns` не считаем: пилот не стартовал):

```sql
SELECT round(100.0 * count(*) FILTER (WHERE status = 'finished')
             / nullif(count(*) FILTER (WHERE status <> 'dns'), 0), 1) AS "Финишировали, %"
FROM race_entry
WHERE $__timeFilter(race_date)
```

**Unit → Percent (0-100)**, **Min 0**, **Max 100**, **Thresholds**: красный до 60, жёлтый до 80, зелёный выше.

> **Show → All values** у Pie chart и Stat: по умолчанию стоит «Calculate» (одно значение на столбец). Если сектор один, а строк в запросе четыре — дело в этой настройке.

> `nullif(..., 0)` защищает от деления на ноль, если в выбранном периоде гонок нет: панель покажет «No data», а не ошибку.

> Сравни Gauge на диапазонах «Last 10 years» и «Last 76 years»: доля финишей в 1950-х и сейчас сильно отличается. Это хороший пример, почему у дашборда должен быть явный диапазон.

### Практика

1. Сделай Stat «Рекорд круга за период» с трассой и пилотом (три столбца: секунды с Unit Duration, трасса, пилот — для текста в Stat выбери **Value options → Fields → Все поля**).
2. Замени Gauge на **Bar gauge** с долей финишей по **каждому** типу трассы (`permanent`, `street`, `oval`).

# Часть III. Дашборд целиком

## Урок 9. Переменные

Переменные превращают статичный дашборд в инструмент: выбрал тип трасс — все панели показывают только их.

**Dashboard settings** (шестерёнка вверху дашборда или Edit → Settings) → **Variables** → **New variable**:

| Поле | Значение |
|---|---|
| Variable type | Query |
| Name | `track_type` |
| Label | Тип трассы |
| Data source | `StudyDB` |
| Query | `SELECT DISTINCT track_type FROM track ORDER BY 1` |
| Multi-value | вкл. |
| Include All option | вкл. |

Вторая переменная `team` по id с понятной подписью. Команд у тебя больше тысячи, поэтому в список берём только те, у которых есть победы:

```sql
SELECT DISTINCT tm.team_id AS id, tm.name
FROM team tm
JOIN car c         ON c.team_id = tm.team_id
JOIN race_entry re ON re.car_id = c.car_id AND re.finish_position = 1
ORDER BY tm.name
```

В редакторе: **Value field** = `id`, **Text field** = `name`, Multi-value + All. **Refresh → On dashboard load**.

Использование в запросах. Добавь условия в Bar chart из урока 7:

```sql
SELECT tm.name AS "Команда",
       count(*) FILTER (WHERE re.finish_position = 1)  AS "Победы",
       count(*) FILTER (WHERE re.finish_position <= 3) AS "Подиумы"
FROM race_entry re
JOIN car   c  ON c.car_id   = re.car_id
JOIN team  tm ON tm.team_id = c.team_id
JOIN track t  ON t.track_id = re.track_id
WHERE $__timeFilter(re.race_date)
  AND t.track_type IN ($track_type)
  AND tm.team_id IN (${team:csv})
GROUP BY tm.team_id, tm.name
ORDER BY 2 DESC
LIMIT 10
```

Для текстового мультивыбора Grafana подставит список в кавычках: `t.track_type IN ('street','oval')`. Для числовых id нужен формат `:csv`: `tm.team_id IN (3,7,12)` без кавычек. Поэтому всегда `IN (...)`, а не `= $var`.

> Запрос переменной `team` проходит по всем заездам и выполняется при каждом открытии дашборда. На 54 тысячах строк это доли секунды, но если станет медленно, поставь **Refresh → Never** и обновляй список вручную кнопкой в настройках переменной.

> Фильтр по команде в Pie chart и Gauge — по командам **машин** в заездах. Не забудь `JOIN car` в этих запросах, иначе `tm.team_id` будет не из чего взять.

Подробнее: [PostgreSQL template variables](https://grafana.com/docs/grafana/latest/datasources/postgres/template-variables/), [Dashboard variables](https://grafana.com/docs/grafana/latest/dashboards/variables/).

### Практика

1. Подключи `$track_type` и `$team` ко всем панелям, где это имеет смысл. Проверь, что при выборе одной команды все панели согласованно меняются.
2. (*) Сделай переменную `driver`, зависящую от `team` (пилоты, ездившие на машинах выбранных команд), и фильтр по ней в таблице.

## Урок 10. Компоновка, сохранение, экспорт

Собираем дашборд в аккуратный вид и сохраняем так, чтобы его можно было сдать и восстановить.

**Компоновка.** Панели перетаскиваются за заголовок и растягиваются за угол. Сетка — 24 колонки. Разумная раскладка:

```
┌──────────┬──────────┬──────────┐
│  Stat    │  Gauge   │   Pie    │   ← верхний ряд: короткие ответы
├──────────┴──────────┴──────────┤
│        Time series             │   ← главный график во всю ширину
├────────────────┬───────────────┤
│   Bar chart    │    Table      │   ← детали
└────────────────┴───────────────┘
```

**Rows.** **Add → Row** — сворачиваемая строка, внутрь которой перетаскиваются панели. Удобно спрятать таблицу деталей.

**Автообновление.** Кнопка обновления вверху справа → интервал (например, 30s). Если параллельно работает генератор из лабы 8, на панелях будут появляться новые гонки.

**Сохранение.** Значок дискеты. Дашборд хранится во встроенной базе Grafana, в томе `grafana-data`.

**Экспорт в JSON.** Кнопка **Export** вверху дашборда → **Export as JSON** → **Download file** (в старых версиях: **Share → Export**). Получится файл с описанием всех панелей, запросов и переменных. Положи его в `lab10/dashboards/racing.json`.

**Импорт.** **Dashboards → New → Import** → загрузить JSON → выбрать источник данных.

> При экспорте включи **Export for sharing externally**, если дашборд будут импортировать в другую Grafana: тогда вместо внутреннего id источника в JSON будет запрос «выбери источник» при импорте. Без этой галочки импорт на другой машине покажет «Data source not found».

> Пароль источника данных в JSON дашборда **не попадает**: дашборд хранит только ссылку на источник. Это нормально и безопасно.

### Практика

1. Разложи панели по макету, сохрани, экспортируй JSON.
2. Удали дашборд и импортируй его обратно из файла.

## Урок 11. Источник данных из файла

Необязательно, но полезно: источник данных, описанный в файле (provisioning), появляется автоматически при запуске контейнера. Не нужно кликать при каждом пересоздании.

`lab10/provisioning/datasources/study.yaml`:

```yaml
apiVersion: 1

datasources:
  - name: StudyDB
    type: postgres
    url: host.docker.internal:5433
    user: grafana_ro
    secureJsonData:
      password: grafana_ro_pass
    jsonData:
      database: study
      sslmode: disable
      postgresVersion: 1700      # 1700 = PostgreSQL 17, как в твоём dockerfile
```

В `docker-compose.yml` добавь том:

```yaml
    volumes:
      - grafana-data:/var/lib/grafana
      - ./provisioning:/etc/grafana/provisioning
```

```bash
docker compose up -d --force-recreate
```

В **Connections → Data sources** появится `StudyDB` с пометкой, что он управляется из файла.

> `type: postgres` — старое имя типа, оно по-прежнему поддерживается. В новых версиях плагин называется `grafana-postgresql-datasource`, подойдут оба.

> Пароль в YAML-файле лежит открытым текстом. Для учебного стенда терпимо, но такой файл не коммитят в публичный репозиторий. Grafana умеет подставлять переменные окружения: `password: $GRAFANA_PG_PASSWORD`.

Дашборды тоже можно подгружать из файлов (`provisioning/dashboards/*.yaml` + папка с JSON), смотри [документацию по provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/).

### Практика

1. Настрой provisioning источника, пересоздай контейнер вместе с томом (`docker compose down -v && docker compose up -d`), импортируй свой JSON-дашборд и проверь, что всё работает без ручной настройки источника.

---

# Итог: дашборд «Гонки»

| # | Панель | Тип | Что показывает | Переменные |
|---|---|---|---|---|
| 1 | Гонки за период | Stat | гонки, пилоты, заезды | track_type, team |
| 2 | Доля финишей | Gauge | финишировавшие среди стартовавших, % | track_type, team |
| 3 | Статусы заездов | Pie chart | finished / dnf / dsq / dns | track_type, team |
| 4 | Заезды по времени | Time series | кварталы, стопкой по статусам | track_type, team |
| 5 | Топ-10 команд | Bar chart | победы и подиумы | track_type, team |
| 6 | Последние гонки | Table | протоколы с лучшим кругом и временем | track_type, team |

Чек-лист сдачи:

- Grafana запущена, источник `StudyDB` проходит Save & test;
- подключение под пользователем только для чтения;
- на дашборде не меньше 5 панелей, среди них Table, Time series и Bar chart;
- диапазон дашборда по умолчанию — годы, а не часы;
- интервалы показаны через секунды и единицу Duration;
- панели реагируют на диапазон времени (`$__timeFilter`) и на переменные;
- дашборд экспортирован в JSON.

# Финальное задание

Сделай второй дашборд «Пилот», не подглядывая в уроки:

- Переменные: страна пилота (мультивыбор) и пилот (зависит от страны, только пилоты с хотя бы одним стартом).
- Панели (не меньше 6):
  - Stat: старты, победы, подиумы, очки выбранного пилота за период (можно взять `fn_driver_career` из лабы 3: `SELECT * FROM fn_driver_career($driver)`);
  - Time series: нарастающий итог очков пилота по гонкам (`sum(...) OVER (ORDER BY race_date)`);
  - Bar chart: результаты по трассам (сколько раз финишировал на каждой месте 1–3);
  - Table: все гонки пилота за период через `fn_driver_season` или запрос с `JOIN`, с раскраской по месту;
  - Pie chart: команды, за которые он выступал (по числу гонок);
  - Gauge: средняя скорость на лучшем круге через `fn_avg_speed` в среднем по гонкам периода.
- Хотя бы одна панель с двумя запросами (A и B) и двумя осями.
- Дашборд экспортирован в JSON, источник данных описан в provisioning.

# Шпаргалка

```bash
docker compose up -d          # http://localhost:3000, admin/admin
```

```sql
-- пользователь только для чтения
CREATE ROLE grafana_ro WITH LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE study TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;

-- Time series (Format: Time series)
SELECT $__timeGroupAlias(ts_col, $__interval), category AS "Серия", count(*) AS "Значение"
FROM t WHERE $__timeFilter(ts_col) GROUP BY 1, 2 ORDER BY 1;

-- Bar chart / Pie chart (Format: Table)
SELECT name AS "Категория", count(*) AS "Значение" FROM t WHERE $__timeFilter(ts_col)
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- Stat / Gauge
SELECT count(*) FROM t WHERE $__timeFilter(ts_col);

-- переменные
WHERE name IN ($var)              -- мультивыбор, строки в кавычках
WHERE id IN (${var_id:csv})       -- числа без кавычек
```

| Симптом | Куда смотреть |
|---|---|
| «Data does not have a time field» | Format = Time series, столбец `time` |
| пустой график | диапазон времени дашборда и `$__timeFilter` |
| один сектор в Pie chart | Value options → Show → All values |
| `permission denied` | права `grafana_ro`, `ALTER DEFAULT PRIVILEGES` |
| реальный SQL с подстановками | Query inspector → Query |

# Источники и что почитать дальше

**Официальная документация**
- [Install Grafana](https://grafana.com/docs/grafana/latest/setup-grafana/installation/) — установка без Docker; ссылка из задания.
- [Run Grafana Docker image](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/) — образы, тома, переменные окружения.
- [PostgreSQL data source](https://grafana.com/docs/grafana/latest/datasources/postgres/) — обзор источника.
- [Configure the PostgreSQL data source](https://grafana.com/docs/grafana/latest/datasources/postgres/configure/) — поля подключения, provisioning, пользователь только для чтения.
- [PostgreSQL query editor](https://grafana.com/docs/grafana/latest/datasources/postgres/query-editor/) — макросы времени, форматы Table и Time series, правила для столбцов.
- [PostgreSQL template variables](https://grafana.com/docs/grafana/latest/datasources/postgres/template-variables/) — переменные на SQL, мультивыбор, `:csv`.
- [Dashboard variables](https://grafana.com/docs/grafana/latest/dashboards/variables/) — переменные в целом, связанные переменные.
- [Visualizations](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/) — все типы панелей и их настройки.
- [Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/) — источники и дашборды из файлов.

**Курсы**
- [Docker: Get started](https://docs.docker.com/get-started/) — если нужно подтянуть Docker.
