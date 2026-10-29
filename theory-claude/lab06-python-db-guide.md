# Доступ к PostgreSQL из Python (лабораторная 6)

Материал к лабораторной 6 «Технология доступа к данным РБД». Строим консольное приложение с меню из 10 пунктов на Python и драйвере psycopg 3. Все запросы выполняются на стороне базы, приложение только отправляет SQL и печатает результат. Схема автогонок из лабы 1, функции и процедуры из лабы 3 (`fn_avg_speed`, `fn_driver_season`, `fn_driver_career`, `pr_disqualify`), база `study` на порту 5433.

В конце ты сможешь:
- подключаться к PostgreSQL из Python и безопасно передавать параметры;
- выполнять запросы любой сложности и печатать результат таблицей;
- вызывать свои функции и процедуры, получать их `RAISE NOTICE` и понимать, когда нужен `commit`;
- создавать таблицы и массово загружать данные через `INSERT` и `COPY`.

Как проходить: по порядку, код набирать руками. Каждый урок добавляет в `app.py` один пункт меню, к уроку 11 получится вся лаба.

**Что нужно знать заранее**

- **Python** (большой раздел, по ходу не объясняется): функции, словари, списки, `with`, исключения, f-строки, виртуальные окружения. Если с этим слабо, сначала пройди первые 9 глав [официального туториала](https://docs.python.org/3/tutorial/).
- **Свои функции и процедуры из лабы 3**: они должны быть созданы в базе. Если пересоздавал контейнер, выполни файлы из `lab-03/01-funcs` и `lab-03/02-stored-procedures` заново.
- **CTE и оконные функции** (лабы 2–3): в уроке 5 только короткое напоминание.

**Содержание**

- Часть I. Основы
  - [Урок 0. Окружение](#урок-0-окружение)
  - [Урок 1. Подключение и скалярный запрос](#урок-1-подключение-и-скалярный-запрос)
  - [Урок 2. Параметры запроса и SQL-инъекции](#урок-2-параметры-запроса-и-sql-инъекции)
  - [Урок 3. Каркас меню и вывод таблиц](#урок-3-каркас-меню-и-вывод-таблиц)
- Часть II. Запросы
  - [Урок 4. Запрос с несколькими JOIN](#урок-4-запрос-с-несколькими-join)
  - [Урок 5. CTE и оконные функции](#урок-5-cte-и-оконные-функции)
  - [Урок 6. Запрос к метаданным](#урок-6-запрос-к-метаданным)
- Часть III. Функции, процедуры, запись
  - [Урок 7. Вызов скалярной и табличной функции](#урок-7-вызов-скалярной-и-табличной-функции)
  - [Урок 8. Вызов процедуры, NOTICE и транзакции](#урок-8-вызов-процедуры-notice-и-транзакции)
  - [Урок 9. Системные функции](#урок-9-системные-функции)
  - [Урок 10. Создание таблицы](#урок-10-создание-таблицы)
  - [Урок 11. Вставка: INSERT и COPY](#урок-11-вставка-insert-и-copy)
- [Итог: готовое приложение](#итог-готовое-приложение)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. Основы

## Урок 0. Окружение

Ставим Python-окружение и драйвер.

```bash
mkdir lab-06 && cd lab-06
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install "psycopg[binary]"
python -c "import psycopg; print(psycopg.__version__)"
```

`psycopg[binary]` ставит драйвер вместе с готовой libpq.

> Есть старый `psycopg2` и новый `psycopg` (версия 3). В интернете много примеров для `psycopg2`. Здесь везде psycopg 3.

Параметры подключения — в переменных окружения. Твой контейнер `study-pg` слушает на порту **5433** (`"5433:5432"` в `docker-compose.yml`):

```bash
export PGHOST=localhost PGPORT=5433 PGDATABASE=study PGUSER=postgres PGPASSWORD=postgres
```

Эти имена стандартные: их понимают и `psql`, и libpq внутри psycopg.

> Частая ошибка — оставить порт 5432 по умолчанию. Если на компьютере ещё стоит локальный PostgreSQL, приложение подключится **к нему**, и ты будешь удивляться, куда пропали таблицы.

### Практика

1. Создай окружение, поставь psycopg и выведи его версию.

## Урок 1. Подключение и скалярный запрос

Пункт 1 лабы: скалярный запрос, возвращающий одно значение.

`db.py`:

```python
import os
import psycopg


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5433"),
        dbname=os.getenv("PGDATABASE", "study"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        autocommit=autocommit,
    )
```

(`autocommit` объясняется в уроке 8, пока он выключен)

`try_scalar.py`:

```python
from db import connect

with connect() as conn:
    cur = conn.execute("SELECT count(DISTINCT (track_id, race_date)) FROM race_entry")
    (total,) = cur.fetchone()
    print("Всего гонок:", total)
```

| Объект | Что это |
|---|---|
| `conn` | соединение с базой |
| `conn.execute(sql)` | создаёт курсор, выполняет запрос, возвращает курсор |
| `cur.fetchone()` | одна строка кортежем (или `None`) |
| `cur.fetchall()` | все строки списком кортежей |

> Гонку определяет пара `(track_id, race_date)`: в один день бывают гонки на разных трассах. `count(DISTINCT race_date)` дал бы меньше.

Как твои типы приходят в Python:

| PostgreSQL | Python |
|---|---|
| `smallint`, `int` | `int` |
| `numeric` | `decimal.Decimal` |
| `date` (`race_date`) | `datetime.date` |
| `interval` (`best_lap`, `total_time`) | `datetime.timedelta` |
| `boolean` | `bool` |

```python
with connect() as conn:
    best = conn.execute("SELECT min(best_lap) FROM race_entry").fetchone()[0]
    print(best, type(best), best.total_seconds())
```

> `timedelta` печатается как `0:01:11.540000`. Для красивого вывода формат делай сам или в SQL: `to_char(best_lap, 'MI:SS.MS')`.

> `with connect() as conn:` в psycopg 3 при выходе делает `commit` (или `rollback` при исключении) и закрывает соединение. В psycopg2 `with` соединение **не** закрывал.

Подробнее: [psycopg: Basic module usage](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

### Практика

1. Выведи одним скалярным запросом имя пилота с наибольшим числом побед.
2. Выведи самый быстрый круг в истории базы в виде `м:сс.ммм` и трассу, где он поставлен.

## Урок 2. Параметры запроса и SQL-инъекции

Почти каждый пункт меню зависит от ввода. Научимся подставлять значения правильно.

Неправильно:

```python
name = input("Пилот: ")
conn.execute(f"SELECT * FROM driver WHERE full_name = '{name}'")   # НЕЛЬЗЯ
```

Ввод `x'; DELETE FROM contract; --` выполнится. Это SQL-инъекция.

Правильно: плейсхолдер `%s` и значения отдельным кортежем.

```python
year = int(input("Сезон: "))
cur = conn.execute("""
    SELECT count(*) FROM race_entry WHERE extract(year FROM race_date) = %s
""", (year,))
print(cur.fetchone()[0])
```

Драйвер передаёт значение отдельно от текста запроса, сервер не исполнит его как SQL.

Даты и интервалы передаются Python-объектами:

```python
from datetime import date, timedelta

conn.execute("SELECT count(*) FROM race_entry WHERE race_date >= %s AND best_lap < %s",
             (date(2020, 1, 1), timedelta(seconds=80)))
```

Именованные параметры:

```python
conn.execute("SELECT * FROM race_entry WHERE driver_id = %(d)s AND race_date = %(dt)s",
             {"d": 20, "dt": date(1950, 5, 13)})
```

> `%s` всегда без кавычек: `WHERE full_name = %s`, а не `'%s'`.

> Кортеж из одного элемента — с запятой: `(year,)`.

> Плейсхолдеры только для **значений**. Имя таблицы так не подставить; для этого `psycopg.sql.Identifier` (урок 6).

> `%` в тексте запроса при наличии параметров удваивается: `LIKE 'Ham%%'`. Лучше передавать шаблон параметром.

Подробнее: [psycopg: Passing parameters to SQL queries](https://www.psycopg.org/psycopg3/docs/basic/params.html).

### Практика

1. Спроси часть имени и выведи пилотов, у кого `full_name` содержит её без учёта регистра, со страной и годом дебюта (не больше 20 строк).
2. Попробуй ввести `' OR 1=1 --`. Убедись, что вернулось ноль строк.

## Урок 3. Каркас меню и вывод таблиц

Каркас: меню, печать результата таблицей, обработка ошибок.

`app.py`:

```python
from datetime import date, timedelta

import psycopg
from db import connect


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, timedelta):              # интервалы как ч:мм:сс.ммм
        total = v.total_seconds()
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}:{int(m):02d}:{s:06.3f}" if h else f"{int(m)}:{s:06.3f}"
    return str(v)


def print_table(cur: psycopg.Cursor) -> None:
    """Печатает результат запроса как таблицу."""
    if cur.description is None:
        print(f"Готово. Затронуто строк: {cur.rowcount}")
        return
    headers = [col.name for col in cur.description]
    rows = cur.fetchall()
    cells = [[fmt(v)[:40] for v in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for r in cells:
        print(" | ".join(c.ljust(w) for c, w in zip(r, widths)))
    print(f"({len(rows)} строк)")


def ask_int(prompt: str, default: int | None = None) -> int:
    raw = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
    if not raw and default is not None:
        return default
    return int(raw)


def ask_date(prompt: str, default: date | None = None) -> date:
    raw = input(f"{prompt} (ГГГГ-ММ-ДД){f' [{default}]' if default else ''}: ").strip()
    if not raw and default is not None:
        return default
    return date.fromisoformat(raw)


def scalar_query(conn):
    cur = conn.execute("SELECT count(DISTINCT (track_id, race_date)) FROM race_entry")
    print("Всего гонок в базе:", cur.fetchone()[0])


ACTIONS = {
    "1": ("Скалярный запрос", scalar_query),
}


def main():
    with connect() as conn:
        while True:
            print("\n=== Автогонки ===")
            for key, (title, _) in ACTIONS.items():
                print(f"{key:>2}. {title}")
            print(" 0. Выход")
            choice = input("> ").strip()
            if choice == "0":
                break
            action = ACTIONS.get(choice)
            if action is None:
                print("Нет такого пункта")
                continue
            try:
                action[1](conn)
            except psycopg.Error as e:
                conn.rollback()
                print("Ошибка базы данных:", e)
            except ValueError as e:
                print("Неверный ввод:", e)


if __name__ == "__main__":
    main()
```

`cur.description` — описания столбцов; у `INSERT`/`CREATE` без `RETURNING` он `None`.

> Зачем `conn.rollback()` в `except`: в режиме по умолчанию psycopg 3 открывает транзакцию на первом запросе. После ошибки она становится «aborted», и все следующие запросы падают с `current transaction is aborted, commands ignored until end of transaction block`, пока не сделать `rollback`.

> `date.fromisoformat("13.05.1950")` бросит `ValueError`, и каркас его поймает. Без `except ValueError` неверная дата роняла бы программу.

### Практика

1. Добавь пункт «s. Свой SQL»: читает запрос с клавиатуры и печатает результат. Проверь, что после запроса с ошибкой меню работает дальше.
2. Проверь `fmt` на `timedelta(hours=2, minutes=13, seconds=23.6)` и `timedelta(seconds=71.54)`.

# Часть II. Запросы

## Урок 4. Запрос с несколькими JOIN

Пункт 2 лабы. Протокол гонки: пилот, машина, команда, трасса, позиции и время.

```python
def join_query(conn):
    last = conn.execute("SELECT max(race_date) FROM race_entry").fetchone()[0]
    race_date = ask_date("Дата гонки", last)
    cur = conn.execute("""
        SELECT t.name                AS track,
               re.finish_position    AS pos,
               d.full_name           AS driver,
               tm.name               AS team,
               c.model               AS car,
               re.grid_position      AS grid,
               re.grid_position - re.finish_position AS gained,
               re.status,
               re.laps_completed     AS laps,
               re.best_lap,
               re.total_time
        FROM race_entry re
        JOIN driver d  ON d.driver_id  = re.driver_id
        JOIN car c     ON c.car_id     = re.car_id
        JOIN team tm   ON tm.team_id   = c.team_id
        JOIN track t   ON t.track_id   = re.track_id
        WHERE re.race_date = %s
        ORDER BY t.name, re.finish_position NULLS LAST, re.grid_position
    """, (race_date,))
    print_table(cur)
```

```python
ACTIONS = {
    "1": ("Скалярный запрос", scalar_query),
    "2": ("Запрос с несколькими JOIN", join_query),
}
```

> `ORDER BY ... NULLS LAST`: у сошедших `finish_position` равен `NULL`, а по умолчанию `NULL` при сортировке по возрастанию идёт в конец только в PostgreSQL. Явное `NULLS LAST` делает намерение понятным и переносимым.

> `gained` у сошедших `NULL`: арифметика с `NULL` даёт `NULL`. Это правильно, «отыграл позиций» для сошедшего не определено.

> Команду берём через машину (`car.team_id`), а не через `contract`. Контракт говорит, за кого пилот числился, а машина — за кого он реально ехал в этой гонке. Это разные вещи, и на защите полезно это проговорить.

### Практика

1. Сделай пункт «Трасса»: пользователь вводит часть названия трассы, выводятся все гонки на ней (дата, победитель, поул, число сошедших). Подсказка: группировка по `(track_id, race_date)` и `FILTER`.

## Урок 5. CTE и оконные функции

Пункт 3 лабы. Напоминание:

- **CTE** (`WITH имя AS (...)`) — именованный подзапрос, читается сверху вниз как шаги;
- **оконная функция** (`... OVER (PARTITION BY ... ORDER BY ...)`) считает по группе строк, не схлопывая их.

Запрос: личный зачёт сезона по современной системе очков (25-18-15-12-10-8-6-4-2-1), место пилота и отставание от лидера.

```python
def cte_window_query(conn):
    last_year = conn.execute("SELECT extract(year FROM max(race_date))::int FROM race_entry").fetchone()[0]
    year = ask_int("Сезон", last_year)
    cur = conn.execute("""
        WITH points AS (
            SELECT re.driver_id,
                   coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[re.finish_position], 0) AS pts,
                   re.finish_position
            FROM race_entry re
            WHERE extract(year FROM re.race_date) = %s
        ),
        standings AS (
            SELECT driver_id,
                   sum(pts)                                AS points,
                   count(*) FILTER (WHERE finish_position = 1)  AS wins,
                   count(*) FILTER (WHERE finish_position <= 3) AS podiums,
                   count(*)                                AS starts
            FROM points
            GROUP BY driver_id
        )
        SELECT rank() OVER (ORDER BY s.points DESC, s.wins DESC)      AS place,
               d.full_name                                            AS driver,
               s.points, s.wins, s.podiums, s.starts,
               first_value(s.points) OVER (ORDER BY s.points DESC) - s.points AS gap
        FROM standings s
        JOIN driver d ON d.driver_id = s.driver_id
        ORDER BY place
        LIMIT 20
    """, (year,))
    print_table(cur)
```

`(ARRAY[25,18,...])[finish_position]` — индекс в массиве: 1-е место даёт 25, 10-е даёт 1, а 11-е и `NULL` (сход) выходят за массив и дают `NULL`, который `coalesce` превращает в 0.

Ещё пример окна: серия финишей пилота подряд через `lag`.

```sql
SELECT race_date, status,
       lag(status) OVER (PARTITION BY driver_id ORDER BY race_date) AS prev_status
FROM race_entry
WHERE driver_id = 20
ORDER BY race_date;
```

| Функция | Что даёт |
|---|---|
| `row_number()` | номер строки в окне без повторов |
| `rank()` / `dense_rank()` | место с повторами (с пропусками / без) |
| `lag(x)` / `lead(x)` | значение из предыдущей / следующей строки |
| `sum(x) OVER (...)` | сумма по окну; с `ORDER BY` — нарастающий итог |
| `first_value(x)` | первое значение окна |

> Система очков 25-18-15… введена в 2010 году; для 1950-х она исторически неверна. Для лабы это неважно, но если спросят — так и скажи: «считаем по единой современной системе, чтобы сезоны были сравнимы».

Подробнее: [Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html), [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html).

### Практика

1. Сделай пункт «Кубок конструкторов сезона»: те же очки, но по командам (через `car.team_id`), с местом и долей очков команды от общей суммы.
2. (*) Нарастающий итог очков лидера по гонкам сезона: `sum(pts) OVER (PARTITION BY driver_id ORDER BY race_date)` — после какой гонки он стал недосягаем?

## Урок 6. Запрос к метаданным

Пункт 4 лабы: запрос к описанию базы. У тебя много ограничений, их интересно показать.

| | `information_schema` | `pg_catalog` |
|---|---|---|
| Стандарт | SQL-стандарт | только PostgreSQL |
| Полнота | основное | всё, включая размеры и статистику |
| Удобство | понятные имена | короче, но нужно знать таблицы |

```python
def metadata_query(conn):
    print_table(conn.execute("""
        SELECT c.conrelid::regclass AS table_name,
               count(*) FILTER (WHERE c.contype = 'p') AS pk,
               count(*) FILTER (WHERE c.contype = 'u') AS uniq,
               count(*) FILTER (WHERE c.contype = 'c') AS checks,
               count(*) FILTER (WHERE c.contype = 'f') AS fks,
               pg_size_pretty(pg_total_relation_size(c.conrelid)) AS size
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public'
        GROUP BY c.conrelid
        ORDER BY checks DESC
    """))
```

`contype`: `p` — первичный ключ, `u` — уникальность, `c` — `CHECK`, `f` — внешний ключ. У `race_entry` будет больше всего `CHECK`-ограничений.

Тексты ограничений выбранной таблицы, имя таблицы тут **значение**:

```python
def table_checks(conn):
    table = input("Таблица: ").strip()
    print_table(conn.execute("""
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = %s::regclass AND contype = 'c'
        ORDER BY conname
    """, (table,)))
```

`%s::regclass` превращает строку `'race_entry'` в идентификатор таблицы. Несуществующее имя даст ошибку `relation ... does not exist`, каркас её поймает.

Свои функции и процедуры — тоже метаданные:

```sql
SELECT p.proname, CASE p.prokind WHEN 'f' THEN 'функция' WHEN 'p' THEN 'процедура' END AS kind,
       pg_get_function_arguments(p.oid) AS args
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
ORDER BY 1;
```

Имя таблицы в `FROM` — через `psycopg.sql`:

```python
from psycopg import sql

table = input("Таблица: ").strip()
query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
print(conn.execute(query).fetchone()[0])
```

Подробнее: [information_schema.columns](https://www.postgresql.org/docs/current/infoschema-columns.html).

### Практика

1. Сделай пункт «Функции и процедуры базы» по запросу выше и проверь, что там есть всё из лабы 3.
2. (*) Найди через метаданные `CHECK`-ограничения, которые ссылаются на текущую дату (`current_date` или `now()` в тексте). Объясни, почему такие ограничения коварны: строка, которая сегодня проходит проверку, через год могла бы не пройти, но PostgreSQL перепроверяет `CHECK` только при вставке и изменении.

# Часть III. Функции, процедуры, запись

## Урок 7. Вызов скалярной и табличной функции

Пункты 5 и 6 лабы. Вызываем твои функции из лабы 3.

Скалярная `fn_avg_speed(p_driver_id int, p_race_date date)` — средняя скорость на лучшем круге, км/ч:

```python
def call_scalar_function(conn):
    driver_id = ask_int("id пилота", 20)
    race_date = ask_date("Дата гонки", date(1950, 5, 13))
    speed = conn.execute("SELECT fn_avg_speed(%s, %s)", (driver_id, race_date)).fetchone()[0]
    print("Средняя скорость на лучшем круге:", f"{speed} км/ч" if speed is not None else "нет данных")
```

> Функция вернёт `NULL` (Python `None`), если пилот в этот день не ехал или у него нет `best_lap` (`dns`, `dsq`). Обработай это при печати, иначе пользователь увидит загадочное `None км/ч`.

Табличная `fn_driver_season(p_driver_id int, p_year int)` — в `FROM`, как таблица:

```python
def call_table_function(conn):
    driver_id = ask_int("id пилота", 657)
    year = ask_int("Сезон", 2000)
    print_table(conn.execute("SELECT * FROM fn_driver_season(%s, %s)", (driver_id, year)))
```

Многооператорная `fn_driver_career(p_driver_id int)` (пункт 6 разрешает и её) — тоже в `FROM`:

```python
def call_career_function(conn):
    driver_id = ask_int("id пилота", 736)
    print_table(conn.execute("SELECT * FROM fn_driver_career(%s)", (driver_id,)))
```

`fn_driver_career` бросает `RAISE EXCEPTION 'Пилот % не найден'` для несуществующего id. В Python это `psycopg.errors.RaiseException`, каркас поймает и покажет текст.

> Если вызвать табличную функцию в `SELECT fn_driver_season(657, 2000)` вместо `FROM`, получишь один столбец составного типа вида `("Monza",...)`. Табличные функции вызывают в `FROM`.

> `function fn_avg_speed(integer, unknown) does not exist`: такое бывает, если передать дату строкой `'1950-05-13'`, а не объектом `date`. psycopg отправит строку без типа, и при перегрузках сервер может не выбрать функцию. С `date(...)` из Python тип будет `date`.

### Практика

1. Сделай пункт, который вызывает `fn_team_tree(p_team_id)` (рекурсивная функция из лабы 3) и печатает дерево с отступами по `level`.
2. (*) Вызови `fn_driver_season` с сортировкой и фильтром прямо в Python-запросе: `SELECT * FROM fn_driver_season(%s, %s) WHERE status = 'finished' ORDER BY finish_position`.

## Урок 8. Вызов процедуры, NOTICE и транзакции

Пункт 7 лабы. Вызываем `pr_disqualify(p_driver_id int, p_race_date date)`: дисквалифицирует финишировавшего пилота и сдвигает места тех, кто был ниже. Процедура меняет данные, поэтому главная тема урока — транзакции.

### NOTICE

Процедура сообщает о результате через `RAISE NOTICE 'Перемещено % значений'`. В `psql` такие сообщения видны сразу, а в Python по умолчанию **теряются**. Подпишемся на них:

```python
def print_notice(diag):
    print(f"[{diag.severity}] {diag.message_primary}")


# в main(), сразу после подключения
conn.add_notice_handler(print_notice)
```

### Вызов

```python
def call_procedure(conn):
    driver_id = ask_int("id пилота")
    race_date = ask_date("Дата гонки")
    conn.execute("CALL pr_disqualify(%s, %s)", (driver_id, race_date))
    if input("Зафиксировать изменения? (y/n): ").strip().lower() == "y":
        conn.commit()
        print("Дисквалификация сохранена")
    else:
        conn.rollback()
        print("Отменено, данные не изменились")
```

Вопрос «зафиксировать?» — удобная страховка для защиты: показал результат, откатил, данные целы. Так же, как ты делал `begin; ... rollback;` в файлах лабы 3.

Проверь до и после:

```sql
SELECT finish_position, driver_id, status FROM race_entry
WHERE track_id = (SELECT track_id FROM race_entry WHERE driver_id = 20 AND race_date = '1950-05-13')
  AND race_date = '1950-05-13'
ORDER BY finish_position NULLS LAST;
```

Как работают транзакции в psycopg 3:

| Режим | Поведение |
|---|---|
| по умолчанию | первый запрос открывает транзакцию; изменения видны другим только после `conn.commit()` |
| `with connect() as conn` | `commit` при выходе, `rollback` при исключении |
| `with conn.transaction():` | отдельный блок с `commit` в конце и `rollback` при ошибке |
| `connect(autocommit=True)` | каждый запрос сразу фиксируется |

> Без `conn.commit()` всё выглядит рабочим: процедура выполнилась, NOTICE пришёл. Но в `psql` из другого окна статус пилота по-прежнему `finished`, а после Ctrl+C изменение пропадёт.

> Ловушка с `with conn.transaction():`: если соединение не в autocommit и до этого выполнялся любой запрос, транзакция уже открыта, и `conn.transaction()` создаёт лишь `SAVEPOINT`. При выходе из блока ничего не фиксируется.

Здесь мы осознанно оставляем режим по умолчанию и явные `commit`/`rollback`: так работает вопрос «зафиксировать?». В итоговом приложении остальные пункты только читают, а пункты 9 и 10 сами делают `commit`.

> Если открытая транзакция долго ждёт ответа пользователя, она держит блокировки на изменённых строках `race_entry`. На учебном стенде это не мешает, но в реальной системе пользовательский ввод внутри транзакции — плохая практика.

> Если у тебя включён триггер аудита из лабы 3 (`tr_race_entry_audit`), каждое `UPDATE` процедуры запишется в `race_entry_audit`. После `rollback` пропадут и эти записи: триггер работает в той же транзакции.

### Практика

1. Вызови `pr_disqualify` для пилота, который не финишировал, и убедись, что меню выводит текст исключения и продолжает работать.
2. Добавь пункт для `pr_close_team(p_team_id)` с тем же вопросом «зафиксировать?» и выводом всех NOTICE (рекурсивные вызовы печатают их с отступами).
3. (*) Проверь, что после `pr_disqualify` в гонке нет «дыр» в местах: запрос, который ищет гонки, где `max(finish_position) <> count(*) FILTER (WHERE status = 'finished')`.

## Урок 9. Системные функции

Пункт 8 лабы: вызвать встроенную функцию PostgreSQL. «Паспорт» базы:

```python
def system_functions(conn):
    cur = conn.execute("""
        SELECT version()                                              AS server,
               current_database()                                     AS db,
               current_user                                           AS "user",
               inet_server_port()                                     AS port_inside,
               pg_size_pretty(pg_database_size(current_database()))   AS db_size,
               pg_size_pretty(pg_total_relation_size('race_entry'))   AS race_entry_size,
               now() - pg_postmaster_start_time()                     AS uptime,
               (SELECT string_agg(extname || ' ' || extversion, ', ') FROM pg_extension) AS extensions
    """)
    for col, value in zip(cur.description, cur.fetchone()):
        print(f"{col.name:>16}: {value}")
```

`inet_server_port()` покажет 5432: внутри контейнера сервер слушает стандартный порт, а 5433 — это проброс на хост. Хорошая деталь для защиты. `pg_extension` покажет и `plpython3u` из твоего `04-ext.sql`.

| Функция | Что возвращает |
|---|---|
| `version()` | версия сервера |
| `current_database()`, `current_user` | текущие база и пользователь |
| `inet_server_addr()`, `inet_server_port()` | адрес и порт сервера изнутри |
| `pg_database_size(name)` | размер базы в байтах |
| `pg_total_relation_size('t')` | размер таблицы с индексами |
| `pg_size_pretty(bytes)` | байты в «12 MB» |
| `pg_postmaster_start_time()` | время запуска сервера |

> `user` — зарезервированное слово, поэтому `AS "user"`.

Подробнее: [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html), [System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html).

### Практика

1. Сделай пункт «Активные соединения» через `pg_stat_activity`: pid, пользователь, состояние, запрос. Пока висит вопрос «зафиксировать?» из урока 8, твоё соединение будет в состоянии `idle in transaction` — проверь это из второго терминала.

## Урок 10. Создание таблицы

Пункт 9 лабы: создать из приложения таблицу по теме. Добавим пит-стопы. У заезда составной ключ `(driver_id, race_date)`, значит и внешний ключ будет составным.

```python
def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_stop (
            driver_id  int      NOT NULL,
            race_date  date     NOT NULL,
            stop_no    smallint NOT NULL CHECK (stop_no BETWEEN 1 AND 10),
            lap        smallint NOT NULL CHECK (lap >= 1),
            duration   interval NOT NULL CHECK (duration BETWEEN '1.5 seconds' AND '10 minutes'),
            tyre       text     NOT NULL CHECK (tyre IN ('soft', 'medium', 'hard', 'intermediate', 'wet')),
            PRIMARY KEY (driver_id, race_date, stop_no),
            FOREIGN KEY (driver_id, race_date) REFERENCES race_entry (driver_id, race_date) ON DELETE CASCADE
        )
    """)
    conn.commit()
    print("Таблица pit_stop готова")
```

`FOREIGN KEY (driver_id, race_date) REFERENCES race_entry (driver_id, race_date)` работает, потому что у `race_entry` первичный ключ ровно на этих двух столбцах.

> Проверку «круг пит-стопа не больше `laps_completed` заезда» `CHECK` сделать не может: он видит только свою строку. Для этого нужен триггер (как в лабе 3) или проверка при вставке. Хороший вопрос на защите: какие правила выражаются `CHECK`, а какие нет.

> DDL в PostgreSQL транзакционный: `CREATE TABLE` без `commit` тоже откатится.

### Практика

1. Сделай свою таблицу по теме (например, `penalty`: штрафы пилотам в гонке, секунды штрафа, причина из списка) с составным внешним ключом на `race_entry`.
2. Добавь пункт «Удалить таблицу» с подтверждением `y/n`.

## Урок 11. Вставка: INSERT и COPY

Пункт 10 лабы. Три способа записи: одна строка, пакет, `COPY`.

Одна строка:

```python
from datetime import date, timedelta

conn.execute("""
    INSERT INTO pit_stop (driver_id, race_date, stop_no, lap, duration, tyre)
    VALUES (%s, %s, %s, %s, %s, %s)
""", (20, date(1950, 5, 13), 1, 35, timedelta(seconds=24.3), "hard"))
conn.commit()
```

Пакет через `executemany` — то же для нескольких строк, `cur.executemany(sql, rows)`.

`COPY` — самый быстрый способ. Сгенерируем пит-стопы для финишировавших заездов: каждому 1–3 стопа на разумных кругах.

```python
import random


def insert_with_copy(conn):
    year = ask_int("Сезон, для которого сгенерировать пит-стопы", 2024)
    entries = conn.execute("""
        SELECT driver_id, race_date, laps_completed
        FROM race_entry
        WHERE status = 'finished' AND extract(year FROM race_date) = %s
          AND NOT EXISTS (SELECT 1 FROM pit_stop p
                          WHERE p.driver_id = race_entry.driver_id AND p.race_date = race_entry.race_date)
    """, (year,)).fetchall()

    rows = 0
    with conn.cursor() as cur:
        with cur.copy("COPY pit_stop (driver_id, race_date, stop_no, lap, duration, tyre) FROM STDIN") as copy:
            for driver_id, race_date, laps in entries:
                n = random.randint(1, 3)
                laps_at = sorted(random.sample(range(2, max(laps, 4)), k=min(n, max(laps - 2, 1))))
                for i, lap in enumerate(laps_at, start=1):
                    copy.write_row((driver_id, race_date, i, lap,
                                    timedelta(seconds=round(random.uniform(2.0, 4.5), 2)),
                                    random.choice(["soft", "medium", "hard"])))
                    rows += 1
    conn.commit()
    print(f"Загружено {rows} пит-стопов для {len(entries)} заездов через COPY")
```

`write_row` сам превращает `date`, `timedelta`, числа в формат `COPY`.

| Способ | Когда |
|---|---|
| `execute` | одна строка |
| `executemany` | десятки–сотни строк |
| `COPY ... FROM STDIN` | тысячи и больше, загрузка из файла |

> `NOT EXISTS` в выборке делает пункт повторяемым: второй запуск для того же сезона не попытается вставить те же пит-стопы и не упадёт на первичном ключе.

> Внешний ключ и `CHECK` проверяются и при `COPY`: одна строка с `duration` меньше 1,5 секунды откатит весь `COPY`.

> `random.sample(range(2, ...))`: пит-стоп на первом круге бывает, но редко; начинаем со второго. `max(laps, 4)` защищает от слишком коротких гонок, где диапазон получился бы пустым.

Подробнее: [psycopg: Using COPY TO and COPY FROM](https://www.psycopg.org/psycopg3/docs/basic/copy.html), [COPY](https://www.postgresql.org/docs/current/sql-copy.html).

### Практика

1. Сделай пункт «Загрузить пит-стопы из CSV» через `COPY ... FROM STDIN WITH (FORMAT csv, HEADER)` и `copy.write(...)` кусками. Положи в файл строку с несуществующим заездом и посмотри, что случится со всей загрузкой.
2. (*) Замерь вставку пит-стопов за один сезон тремя способами (`execute` в цикле, `executemany`, `COPY`) и выведи сравнение.

---

# Итог: готовое приложение

```
lab-06/
├── db.py
└── app.py
```

`db.py` из урока 1. `app.py` целиком:

```python
import random
import time
from datetime import date, timedelta

import psycopg
from db import connect


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, timedelta):
        total = v.total_seconds()
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h)}:{int(m):02d}:{s:06.3f}" if h else f"{int(m)}:{s:06.3f}"
    return str(v)


def print_table(cur):
    if cur.description is None:
        print(f"Готово. Затронуто строк: {cur.rowcount}")
        return
    headers = [c.name for c in cur.description]
    rows = cur.fetchall()
    cells = [[fmt(v)[:40] for v in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for r in cells:
        print(" | ".join(c.ljust(w) for c, w in zip(r, widths)))
    print(f"({len(rows)} строк)")


def ask_int(prompt, default=None):
    raw = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
    if not raw and default is not None:
        return default
    return int(raw)


def ask_date(prompt, default=None):
    raw = input(f"{prompt} (ГГГГ-ММ-ДД){f' [{default}]' if default else ''}: ").strip()
    if not raw and default is not None:
        return default
    return date.fromisoformat(raw)


def print_notice(diag):
    print(f"[{diag.severity}] {diag.message_primary}")


# 1
def scalar_query(conn):
    print("Всего гонок в базе:",
          conn.execute("SELECT count(DISTINCT (track_id, race_date)) FROM race_entry").fetchone()[0])


# 2
def join_query(conn):
    last = conn.execute("SELECT max(race_date) FROM race_entry").fetchone()[0]
    race_date = ask_date("Дата гонки", last)
    print_table(conn.execute("""
        SELECT t.name AS track, re.finish_position AS pos, d.full_name AS driver,
               tm.name AS team, c.model AS car, re.grid_position AS grid,
               re.grid_position - re.finish_position AS gained, re.status,
               re.laps_completed AS laps, re.best_lap, re.total_time
        FROM race_entry re
        JOIN driver d ON d.driver_id = re.driver_id
        JOIN car c    ON c.car_id    = re.car_id
        JOIN team tm  ON tm.team_id  = c.team_id
        JOIN track t  ON t.track_id  = re.track_id
        WHERE re.race_date = %s
        ORDER BY t.name, re.finish_position NULLS LAST, re.grid_position
    """, (race_date,)))


# 3
def cte_window_query(conn):
    last_year = conn.execute("SELECT extract(year FROM max(race_date))::int FROM race_entry").fetchone()[0]
    year = ask_int("Сезон", last_year)
    print_table(conn.execute("""
        WITH points AS (
            SELECT re.driver_id, re.finish_position,
                   coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[re.finish_position], 0) AS pts
            FROM race_entry re
            WHERE extract(year FROM re.race_date) = %s
        ),
        standings AS (
            SELECT driver_id, sum(pts) AS points,
                   count(*) FILTER (WHERE finish_position = 1) AS wins,
                   count(*) FILTER (WHERE finish_position <= 3) AS podiums,
                   count(*) AS starts
            FROM points GROUP BY driver_id
        )
        SELECT rank() OVER (ORDER BY s.points DESC, s.wins DESC) AS place,
               d.full_name AS driver, s.points, s.wins, s.podiums, s.starts,
               first_value(s.points) OVER (ORDER BY s.points DESC) - s.points AS gap
        FROM standings s JOIN driver d ON d.driver_id = s.driver_id
        ORDER BY place
        LIMIT 20
    """, (year,)))


# 4
def metadata_query(conn):
    print_table(conn.execute("""
        SELECT c.conrelid::regclass AS table_name,
               count(*) FILTER (WHERE c.contype = 'p') AS pk,
               count(*) FILTER (WHERE c.contype = 'u') AS uniq,
               count(*) FILTER (WHERE c.contype = 'c') AS checks,
               count(*) FILTER (WHERE c.contype = 'f') AS fks,
               pg_size_pretty(pg_total_relation_size(c.conrelid)) AS size
        FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public'
        GROUP BY c.conrelid
        ORDER BY checks DESC
    """))


# 5
def call_scalar_function(conn):
    driver_id = ask_int("id пилота", 20)
    race_date = ask_date("Дата гонки", date(1950, 5, 13))
    speed = conn.execute("SELECT fn_avg_speed(%s, %s)", (driver_id, race_date)).fetchone()[0]
    print("Средняя скорость на лучшем круге:", f"{speed} км/ч" if speed is not None else "нет данных")


# 6
def call_table_function(conn):
    driver_id = ask_int("id пилота", 736)
    print_table(conn.execute("SELECT * FROM fn_driver_career(%s)", (driver_id,)))
    if input("Показать гонки пилота за сезон? (y/n): ").strip().lower() == "y":
        year = ask_int("Сезон")
        print_table(conn.execute("SELECT * FROM fn_driver_season(%s, %s)", (driver_id, year)))


# 7
def call_procedure(conn):
    driver_id = ask_int("id пилота")
    race_date = ask_date("Дата гонки")
    conn.execute("CALL pr_disqualify(%s, %s)", (driver_id, race_date))
    if input("Зафиксировать изменения? (y/n): ").strip().lower() == "y":
        conn.commit()
        print("Дисквалификация сохранена")
    else:
        conn.rollback()
        print("Отменено, данные не изменились")


# 8
def system_functions(conn):
    cur = conn.execute("""
        SELECT version() AS server, current_database() AS db, current_user AS "user",
               inet_server_port() AS port_inside,
               pg_size_pretty(pg_database_size(current_database())) AS db_size,
               now() - pg_postmaster_start_time() AS uptime,
               (SELECT string_agg(extname || ' ' || extversion, ', ') FROM pg_extension) AS extensions
    """)
    for col, value in zip(cur.description, cur.fetchone()):
        print(f"{col.name:>12}: {value}")


# 9
def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_stop (
            driver_id int NOT NULL,
            race_date date NOT NULL,
            stop_no   smallint NOT NULL CHECK (stop_no BETWEEN 1 AND 10),
            lap       smallint NOT NULL CHECK (lap >= 1),
            duration  interval NOT NULL CHECK (duration BETWEEN '1.5 seconds' AND '10 minutes'),
            tyre      text NOT NULL CHECK (tyre IN ('soft', 'medium', 'hard', 'intermediate', 'wet')),
            PRIMARY KEY (driver_id, race_date, stop_no),
            FOREIGN KEY (driver_id, race_date) REFERENCES race_entry (driver_id, race_date) ON DELETE CASCADE
        )
    """)
    conn.commit()
    print("Таблица pit_stop готова")


# 10
def insert_with_copy(conn):
    year = ask_int("Сезон, для которого сгенерировать пит-стопы", 2024)
    entries = conn.execute("""
        SELECT driver_id, race_date, laps_completed FROM race_entry
        WHERE status = 'finished' AND extract(year FROM race_date) = %s
          AND NOT EXISTS (SELECT 1 FROM pit_stop p
                          WHERE p.driver_id = race_entry.driver_id AND p.race_date = race_entry.race_date)
    """, (year,)).fetchall()
    t = time.perf_counter()
    rows = 0
    with conn.cursor() as cur:
        with cur.copy("COPY pit_stop (driver_id, race_date, stop_no, lap, duration, tyre) FROM STDIN") as copy:
            for driver_id, race_date, laps in entries:
                n = random.randint(1, 3)
                laps_at = sorted(random.sample(range(2, max(laps, 4)), k=min(n, max(laps - 2, 1))))
                for i, lap in enumerate(laps_at, start=1):
                    copy.write_row((driver_id, race_date, i, lap,
                                    timedelta(seconds=round(random.uniform(2.0, 4.5), 2)),
                                    random.choice(["soft", "medium", "hard"])))
                    rows += 1
    conn.commit()
    print(f"Загружено {rows} пит-стопов для {len(entries)} заездов за {time.perf_counter() - t:.2f} с")


ACTIONS = {
    "1": ("Скалярный запрос: число гонок", scalar_query),
    "2": ("JOIN: протокол гонки", join_query),
    "3": ("CTE + окна: личный зачёт сезона", cte_window_query),
    "4": ("Метаданные: ограничения по таблицам", metadata_query),
    "5": ("Скалярная функция fn_avg_speed", call_scalar_function),
    "6": ("Многооператорная/табличная функция fn_driver_career / fn_driver_season", call_table_function),
    "7": ("Процедура pr_disqualify", call_procedure),
    "8": ("Системные функции", system_functions),
    "9": ("Создать таблицу pit_stop", create_table),
    "10": ("Вставка пит-стопов через COPY", insert_with_copy),
}


def main():
    with connect() as conn:
        conn.add_notice_handler(print_notice)
        while True:
            print("\n=== Автогонки ===")
            for key, (title, _) in ACTIONS.items():
                print(f"{key:>2}. {title}")
            print(" 0. Выход")
            choice = input("> ").strip()
            if choice == "0":
                break
            action = ACTIONS.get(choice)
            if action is None:
                print("Нет такого пункта")
                continue
            try:
                action[1](conn)
                conn.rollback()       # закрыть транзакцию после пунктов, которые только читали
            except psycopg.Error as e:
                conn.rollback()
                print("Ошибка базы данных:", e)
            except ValueError as e:
                conn.rollback()
                print("Неверный ввод:", e)


if __name__ == "__main__":
    main()
```

> `conn.rollback()` после каждого пункта: в режиме без autocommit даже `SELECT` открывает транзакцию, и без этого соединение висело бы в `idle in transaction` между пунктами меню. Пункты, которые меняют данные (7, 9, 10), уже сами сделали `commit` или `rollback`, так что для них это пустая операция.

> Пункт 10 зависит от пункта 9: на защите сначала 9, потом 10.

# Финальное задание

Сделай второе приложение `stats.py` с меню по другим данным, не копируя код из уроков:

- Подключение через переменные окружения; при неверном порте или пароле понятное сообщение, а не трассировка.
- Пункты:
  1. скалярный: процент сходов (`dnf`) за всю историю;
  2. JOIN: все контракты пилота с командами и числом гонок, проведённых за каждую команду (через машины);
  3. CTE + окно: для каждой трассы рекорд круга, кто и когда его поставил, и насколько он быстрее второго лучшего результата;
  4. метаданные: все внешние ключи базы с таблицами и столбцами на обоих концах;
  5–7: `fn_avg_speed`, `fn_team_tree`, `pr_close_team` (с вопросом «зафиксировать?» и выводом NOTICE);
  8. системная функция: размеры всех таблиц по убыванию;
  9. создание таблицы `penalty`;
  10. загрузка штрафов из CSV через `COPY`.
- Каждый пункт переживает ошибку базы и неверный ввод без падения.
- Отдельный пункт «Экспорт результата последнего запроса в CSV».

# Шпаргалка

```python
import psycopg
from psycopg import sql
from datetime import date, timedelta

conn = psycopg.connect()                     # PGHOST=localhost PGPORT=5433 PGDATABASE=study ...
conn.add_notice_handler(lambda d: print(d.message_primary))   # RAISE NOTICE

cur = conn.execute("SELECT ... WHERE race_date = %s", (date(1950, 5, 13),))
cur.fetchone()  cur.fetchall()  cur.description  cur.rowcount
# date ↔ datetime.date, interval ↔ datetime.timedelta, numeric ↔ Decimal

conn.execute("SELECT fn_avg_speed(%s, %s)", (20, date(1950, 5, 13)))
conn.execute("SELECT * FROM fn_driver_season(%s, %s)", (657, 2000))
conn.execute("CALL pr_disqualify(%s, %s)", (20, date(1950, 5, 13)))
conn.commit()   conn.rollback()

cur.executemany("INSERT ... VALUES (%s, %s)", rows)
with cur.copy("COPY t (a, b) FROM STDIN") as copy:
    copy.write_row((1, timedelta(seconds=2.4)))

sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
```

```sql
-- очки по позиции
coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[finish_position], 0)
-- гонка = (track_id, race_date)
-- метаданные
pg_constraint (contype p/u/c/f)  pg_get_constraintdef(oid)  pg_proc (prokind f/p)  pg_extension
```

# Источники и что почитать дальше

**Официальная документация**
- [psycopg 3: Basic module usage](https://www.psycopg.org/psycopg3/docs/basic/usage.html) — соединения, курсоры, транзакции, `with`.
- [psycopg 3: Passing parameters](https://www.psycopg.org/psycopg3/docs/basic/params.html) — плейсхолдеры, почему нельзя f-строки, `psycopg.sql`.
- [psycopg 3: COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html) — `write_row`, загрузка файлов, выгрузка.
- [PostgreSQL: Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html) и [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html) — для пункта 3.
- [PostgreSQL: information_schema.columns](https://www.postgresql.org/docs/current/infoschema-columns.html) — для пункта 4.
- [PostgreSQL: System Information Functions](https://www.postgresql.org/docs/current/functions-info.html) — для пункта 8.

**Курсы**
- [The Python Tutorial](https://docs.python.org/3/tutorial/) — если нужно подтянуть сам Python.
