# Redis как кэш для PostgreSQL (лабораторная 9)

Материал к лабораторной 9 «In-Memory DataBase на примере Redis». Строим приложение, которое каждые 5 секунд считает статистику по базе двумя способами: напрямую в PostgreSQL и через Redis как кэш. Параллельно другой поток каждые 10 секунд добавляет, удаляет или меняет строки. Замеряем время и строим графики. Схема автогонок из лабы 1, основная таблица `race_entry` (54 тысячи заездов), база `study` в контейнере `study-pg` на порту 5433.

В конце ты сможешь:
- поднять Redis и работать с ним из `redis-cli` и из Python;
- реализовать кэширование результата запроса по схеме cache-aside;
- правильно сбрасывать кэш при изменении данных;
- поставить честный замер и объяснить графики.

Как проходить: по порядку, код набирать руками. Строим одно приложение `lab09.py` и скрипт графиков `plot.py`, каждый урок что-то в них добавляет.

**Что нужно знать заранее**

- **Docker и Docker Compose** (большой раздел, по ходу не объясняется): `docker compose up -d`, порты, `docker exec`. Если слабо, сначала [Docker: Get started](https://docs.docker.com/get-started/).
- **Python и psycopg** на уровне лабы 6: подключение, параметры, `autocommit`.
- **Потоки в Python** (`threading`) — используем самый минимум, объясняется в уроке 7.

**Содержание**

- Часть I. Redis
  - [Урок 0. Зачем кэш и что будем мерить](#урок-0-зачем-кэш-и-что-будем-мерить)
  - [Урок 1. Redis в Docker и redis-cli](#урок-1-redis-в-docker-и-redis-cli)
  - [Урок 2. Redis из Python](#урок-2-redis-из-python)
- Часть II. Запрос и кэш
  - [Урок 3. Данные для честного замера](#урок-3-данные-для-честного-замера)
  - [Урок 4. Статистический запрос](#урок-4-статистический-запрос)
  - [Урок 5. Cache-aside](#урок-5-cache-aside)
  - [Урок 6. Инвалидация кэша](#урок-6-инвалидация-кэша)
- Часть III. Эксперимент
  - [Урок 7. Поток изменений](#урок-7-поток-изменений)
  - [Урок 8. Цикл замеров](#урок-8-цикл-замеров)
  - [Урок 9. Графики](#урок-9-графики)
  - [Урок 10. Анализ результатов](#урок-10-анализ-результатов)
  - [Урок 11. Инвалидация по событию из базы](#урок-11-инвалидация-по-событию-из-базы)
- [Итог: готовое приложение](#итог-готовое-приложение)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. Redis

## Урок 0. Зачем кэш и что будем мерить

Redis — база данных «ключ → значение», которая держит всё в оперативной памяти. Чтение по ключу занимает доли миллисекунды. PostgreSQL на тот же агрегирующий запрос тратит миллисекунды и больше: читает страницы таблиц, соединяет, группирует.

Идея кэша: результат дорогого запроса один раз положить в Redis, а дальше отдавать оттуда. Проблема: если данные в PostgreSQL изменились, в кэше лежит **устаревший** результат. Вся лаба про этот компромисс.

| Режим | Что происходит при запросе | Плюс | Минус |
|---|---|---|---|
| Напрямую в БД | каждый раз считаем в PostgreSQL | всегда свежие данные | медленно, нагружает БД |
| Через Redis | берём из Redis, если есть; иначе считаем и кладём | быстро | нужно вовремя сбрасывать кэш |

Что требует задание:

| | Без изменений | INSERT каждые 10 с | DELETE каждые 10 с | UPDATE каждые 10 с |
|---|---|---|---|---|
| Запрос в БД каждые 5 с | замер | замер | замер | замер |
| Запрос через Redis каждые 5 с | замер | замер | замер | замер |

Восемь серий замеров, по ним графики.

Главный вопрос для защиты: **почему при изменениях раз в 10 секунд и запросах раз в 5 секунд кэш помогает только наполовину**. К уроку 10 ответ станет очевиден.

### Практика

1. До всех замеров запиши гипотезу: во сколько раз Redis будет быстрее БД в сценарии «без изменений» и в сценарии «INSERT каждые 10 с». В уроке 10 сравнишь.

## Урок 1. Redis в Docker и redis-cli

Пункт 1 лабы: установить Redis. Через Docker это одна команда.

`lab09/docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:8.8.3
    container_name: redis
    ports:
      - "6379:6379"
```

```bash
cd lab09
docker compose up -d
docker exec -it redis redis-cli ping      # PONG
```

`redis-cli` — консольный клиент:

```bash
docker exec -it redis redis-cli --raw
```

```
127.0.0.1:6379> SET greeting "привет"
OK
127.0.0.1:6379> GET greeting
привет
127.0.0.1:6379> SET stats:test "[1,2,3]" EX 30
OK
127.0.0.1:6379> TTL stats:test
27
127.0.0.1:6379> DEL stats:test
1
127.0.0.1:6379> GET stats:test

```

`--raw` выводит текст как есть; без него кириллица показывается байтами.

| Команда | Что делает |
|---|---|
| `SET key value` | записать строку |
| `SET key value EX 60` | записать с временем жизни 60 секунд |
| `GET key` | прочитать (`nil`, если нет) |
| `DEL key` | удалить |
| `EXISTS key` | есть ли ключ |
| `TTL key` | сколько секунд осталось (`-1` — вечно, `-2` — ключа нет) |
| `EXPIRE key 60` | задать время жизни существующему ключу |
| `SCAN 0 MATCH stats:*` | найти ключи по шаблону, порциями |
| `INFO stats` | статистика сервера, в том числе `keyspace_hits` и `keyspace_misses` |
| `FLUSHDB` | удалить все ключи текущей базы |

> `KEYS stats:*` тоже ищет по шаблону, но блокирует Redis, пока не переберёт все ключи. Привыкай к `SCAN`.

> Двоеточие в имени ключа (`stats:all_time`) — соглашение, для Redis это обычный символ. Инструменты вроде RedisInsight группируют ключи по нему как по папкам.

Кроме строк есть хеши (`HSET`), списки (`LPUSH`), множества (`SADD`), сортированные множества (`ZADD`). Для кэша результата запроса достаточно строки с JSON.

Подробнее: [Redis data types](https://redis.io/docs/latest/develop/data-types/), [SET](https://redis.io/docs/latest/commands/set/).

### Практика

1. Положи ключ с `EX 10`, подожди и проверь `TTL` и `GET` до и после истечения.
2. Выполни несколько `GET` существующих и несуществующих ключей и посмотри, как меняются `keyspace_hits` и `keyspace_misses` в `INFO stats`.

## Урок 2. Redis из Python

Подключаемся к Redis из Python библиотекой `redis` (redis-py).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install redis "psycopg[binary]" matplotlib
```

```python
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)
print(r.ping())                        # True

r.set("greeting", "привет", ex=30)
print(r.get("greeting"))               # привет
print(r.ttl("greeting"))               # ~30
r.delete("greeting")
print(r.get("greeting"))               # None
```

`decode_responses=True` — библиотека сама декодирует байты в `str`. Без него `r.get(...)` вернёт `b'...'`.

Результат запроса — список строк. Redis хранит строки, поэтому сериализуем в JSON:

```python
import json
from decimal import Decimal

from datetime import timedelta

rows = [("Lewis Hamilton", "United Kingdom", 356, 105, 4639, timedelta(seconds=74.26))]
r.set("demo", json.dumps(rows, default=str), ex=60)
print(json.loads(r.get("demo")))
# [['Lewis Hamilton', 'United Kingdom', 356, 105, 4639, '0:01:14.260000']]
```

> `json.dumps` не умеет `timedelta` (так приходит `interval`), `date` и `Decimal` и падает с `TypeError`. `default=str` превращает их в строки. Обратно они вернутся строками: `'0:01:14.260000'` вместо `timedelta`. Для показа статистики нормально, для вычислений нужно разбирать обратно или класть в кэш секунды (`.total_seconds()`).

> Кортежи после `json.loads` становятся списками. Если сравниваешь результат из кэша и из БД (урок 6), приводи к одному виду.

Подробнее: [redis-py guide](https://redis.io/docs/latest/develop/clients/redis-py/), [redis-py docs](https://redis.readthedocs.io/en/stable/).

### Практика

1. Напиши функции `cache_set_json(r, key, obj, ttl)` и `cache_get_json(r, key)` (возвращает `None`, если ключа нет). Проверь на словаре с `Decimal` внутри.

# Часть II. Запрос и кэш

## Урок 3. Данные для честного замера

На таблице из 50 строк любой запрос выполняется за доли миллисекунды, и разницы на графике не будет видно. Тебе повезло: в `race_entry` уже 54 тысячи заездов за 76 лет, этого достаточно, чтобы запрос по всей истории занимал десятки миллисекунд.

Проверь:

```sql
SELECT count(*), min(race_date), max(race_date) FROM race_entry;
```

Подготовим **тестовую трассу**. Писатель (урок 7) будет добавлять, менять и удалять гонки только на ней. Так сценарий DELETE не испортит настоящие данные, а после эксперимента всё легко убрать.

`seed.sql`:

```sql
INSERT INTO track (name, country, length_km, track_type, opened_year)
VALUES ('Lab09 Test Ring', 'Russia', 4.20, 'permanent', 2026)
ON CONFLICT (name, country) DO NOTHING;

SELECT track_id FROM track WHERE name = 'Lab09 Test Ring';
```

```bash
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d study -f seed.sql
```

`ON CONFLICT (name, country)` работает благодаря твоему `uq_track`: повторный запуск не создаст вторую трассу.

Уборка после эксперимента:

```sql
DELETE FROM race_entry WHERE track_id = (SELECT track_id FROM track WHERE name = 'Lab09 Test Ring');
DELETE FROM track WHERE name = 'Lab09 Test Ring';
```

> Если у тебя включён триггер аудита из лабы 3 (`tr_race_entry_audit`), каждое изменение писателя запишется ещё и в `race_entry_audit`. Это замедлит запись, но на чтение (которое мы меряем) не влияет. На защите можно показать, что аудит видит все изменения эксперимента.

> Если `pit_stop` из лабы 6 существует, удаление заездов каскадно удалит их пит-стопы (`ON DELETE CASCADE`). На тестовой трассе пит-стопов нет, так что это ни на что не влияет.

> (*) Если хочется более заметной разницы, увеличь данные: прогони генератор из лабы 8 через NiFi на ночь или напиши `INSERT ... SELECT` по образцу генератора. Но и на 54 тысячах эффект кэша виден отлично.

### Практика

1. Создай тестовую трассу и запомни её `track_id`.
2. Посчитай, сколько гонок в базе приходится на один день максимум (`GROUP BY race_date ORDER BY count(DISTINCT track_id) DESC`). Это понадобится, чтобы понять, почему писатель выбирает дату осторожно.

## Урок 4. Статистический запрос

Пункт 2 лабы: запрос, получающий статистику. Вечный рейтинг пилотов за всю историю: старты, победы, подиумы, очки по современной системе (25-18-15-12-10-8-6-4-2-1), пройденные круги, лучший круг и число команд.

```sql
SELECT d.full_name                                                       AS driver,
       d.country,
       count(*)                                                          AS starts,
       count(*) FILTER (WHERE re.finish_position = 1)                    AS wins,
       count(*) FILTER (WHERE re.finish_position <= 3)                   AS podiums,
       sum(coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[re.finish_position], 0)) AS points,
       sum(re.laps_completed)                                            AS laps,
       min(re.best_lap)                                                  AS best_lap,
       count(DISTINCT c.team_id)                                         AS teams
FROM race_entry re
JOIN driver d ON d.driver_id = re.driver_id
JOIN car c    ON c.car_id    = re.car_id
GROUP BY d.driver_id, d.full_name, d.country
ORDER BY points DESC
LIMIT 10;
```

`(ARRAY[25,18,...])[finish_position]` — индекс в массиве: 1-е место даёт 25, 11-е и сход (`NULL`) выходят за массив и через `coalesce` дают 0.

Посмотри, сколько он стоит:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... ;   -- запрос выше
```

`Execution Time` в конце вывода — порядок того, что будем ускорять.

> `count(DISTINCT ...)` заметно дороже обычного `count(*)`: PostgreSQL сортирует или хеширует значения. Хороший кандидат на кэширование.

> Запрос агрегирует **всю** таблицу, индекс тут не поможет. Ускорить базу могло бы материализованное представление (`CREATE MATERIALIZED VIEW ... ; REFRESH ...`), но это тот же кэш, только внутри PostgreSQL, и его так же нужно обновлять при изменениях. Хорошая тема для вывода на защите.

`lab09.py`, начало:

```python
import json
import os
import time

import psycopg
import redis

STATS_SQL = """
SELECT d.full_name AS driver, d.country,
       count(*) AS starts,
       count(*) FILTER (WHERE re.finish_position = 1) AS wins,
       count(*) FILTER (WHERE re.finish_position <= 3) AS podiums,
       sum(coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[re.finish_position], 0)) AS points,
       sum(re.laps_completed) AS laps,
       min(re.best_lap) AS best_lap,
       count(DISTINCT c.team_id) AS teams
FROM race_entry re
JOIN driver d ON d.driver_id = re.driver_id
JOIN car c    ON c.car_id    = re.car_id
GROUP BY d.driver_id, d.full_name, d.country
ORDER BY points DESC
LIMIT 10
"""


def connect_db() -> psycopg.Connection:
    # параметры из PGHOST, PGPORT=5433, PGDATABASE=study, PGUSER, PGPASSWORD
    return psycopg.connect(autocommit=True)


def connect_redis() -> redis.Redis:
    return redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)


def query_db(conn) -> tuple[list, float]:
    """Запрос напрямую в PostgreSQL. Возвращает строки и время в миллисекундах."""
    t0 = time.perf_counter()
    rows = conn.execute(STATS_SQL).fetchall()
    return rows, (time.perf_counter() - t0) * 1000


if __name__ == "__main__":
    with connect_db() as conn:
        rows, ms = query_db(conn)
        for row in rows:
            print(row)
        print(f"{ms:.2f} мс")
```

`autocommit=True`: каждый `SELECT` — отдельная короткая транзакция. Держать одну долгую открытую транзакцию в цикле замеров плохо: она мешает `VACUUM` убирать мёртвые строки.

`time.perf_counter()` — точный таймер для интервалов. `time.time()` для этого не годится: он может прыгать при синхронизации часов.

### Практика

1. Запусти `lab09.py` несколько раз подряд. Первый запуск обычно медленнее: данные ещё не в кэше PostgreSQL (shared buffers). Запиши время первого и последующих.
2. (*) Придумай свой статистический запрос (например, рекорд круга на каждой трассе с автором) и замерь его через `EXPLAIN ANALYZE`.

## Урок 5. Cache-aside

Пункт 3.2: запрос через Redis как кэш. Схема **cache-aside** (кэш сбоку):

1. Пробуем прочитать ключ из Redis.
2. Есть — это **hit**, отдаём.
3. Нет — это **miss**: считаем в PostgreSQL, кладём результат в Redis с временем жизни, отдаём.

```python
CACHE_KEY = "stats:all_time:v1"
CACHE_TTL = 60          # секунд, страховка на случай, если инвалидация не сработает


def query_cached(conn, r) -> tuple[list, float, bool]:
    """Запрос через кэш. Возвращает строки, время в мс и признак попадания в кэш."""
    t0 = time.perf_counter()
    raw = r.get(CACHE_KEY)
    if raw is not None:
        rows = json.loads(raw)
        hit = True
    else:
        rows = [list(row) for row in conn.execute(STATS_SQL).fetchall()]
        r.set(CACHE_KEY, json.dumps(rows, default=str), ex=CACHE_TTL)
        hit = False
    return rows, (time.perf_counter() - t0) * 1000, hit
```

Проверка:

```python
with connect_db() as conn:
    r = connect_redis()
    r.delete(CACHE_KEY)
    for i in range(3):
        _, ms, hit = query_cached(conn, r)
        print(f"{'HIT ' if hit else 'MISS'} {ms:.2f} мс")
```

```
MISS 71.80 мс
HIT  0.37 мс
HIT  0.25 мс
```

Время miss чуть больше прямого запроса: добавились сериализация и `SET`.

> В ключе версия (`:v1`). Поменяешь `STATS_SQL` — поменяй версию, иначе кэш отдаст результат старого запроса (практика 2). Если бы период задавал пользователь, он тоже был бы частью ключа: `stats:season:2024:v1`.

> TTL здесь страховка: если какой-то путь изменения данных забудет сбросить кэш (урок 6), устаревшие данные проживут не дольше минуты.

Подробнее: [Redis: patterns](https://redis.io/docs/latest/develop/use/patterns/).

### Практика

1. Поставь `CACHE_TTL = 10`, запроси статистику, подожди 11 секунд, запроси снова. Должен быть miss.
2. Измени `STATS_SQL` (например, `LIMIT 5`), но не меняй ключ. Что вернулось и почему? Как это предотвратить? (Подсказка: версия в имени ключа.)

## Урок 6. Инвалидация кэша

Пункт 3 требует, чтобы приложение «учитывало возможное добавление, удаление и изменение данных». Значит, после изменения данных кэш должен перестать отдавать старый результат.

Увидим проблему. В Python:

```python
with connect_db() as conn:
    r = connect_redis()
    rows, _, _ = query_cached(conn, r)
    print(rows[0])
```

В `psql` добавь лидеру рейтинга победу на тестовой трассе (подставь его `driver_id` и `track_id` трассы из урока 3):

```sql
INSERT INTO race_entry (driver_id, car_id, track_id, status, grid_position, finish_position,
                        best_lap, total_time, race_date, laps_completed)
SELECT <driver_id лидера>, 1, <id тестовой трассы>, 'finished', 1, 1,
       interval '00:01:20', interval '01:10:00', current_date, 50;
```

Лидер получил ещё 25 очков и победу, а через кэш — всё по-старому.

Способы сбросить кэш:

| Способ | Как | Плюсы | Минусы |
|---|---|---|---|
| Только TTL | ключ живёт N секунд | ничего не надо делать | до N секунд отдаём старые данные |
| Явный сброс при записи | код, который пишет в БД, делает `r.delete(key)` | данные свежие сразу | каждый, кто пишет, должен знать про кэш |
| Событие из базы | триггер в PostgreSQL шлёт `NOTIFY`, слушатель удаляет ключ | ловит любые изменения, даже из `psql` | сложнее, нужен постоянный слушатель |

В этой лабе пишет наше же приложение (урок 7), поэтому основной способ — явный сброс после записи, TTL — страховка. Вариант с событием из базы — в уроке 11.

```python
def invalidate(r) -> None:
    r.delete(CACHE_KEY)
```

> Порядок важен: сначала запись в БД и `commit`, **потом** `delete`. Если удалить ключ до коммита, параллельный читатель может получить miss, посчитать по старым данным и положить устаревший результат обратно.

> Обратный вариант: после записи сразу пересчитать и положить новый результат. Следующий читатель не получит miss, но пересчёт будет на каждую запись, даже если никто не читает.

### Практика

1. Повтори эксперимент на тестовой трассе, но после `INSERT` вызови `invalidate(r)` из Python. Убедись, что следующий запрос — miss и у лидера стало больше побед.
2. Сравни результат без кэша и через кэш после инвалидации. Учти разницу типов из урока 2.

# Часть III. Эксперимент

## Урок 7. Поток изменений

Нужен «писатель», который каждые 10 секунд меняет данные, пока основной цикл каждые 5 секунд читает. Запустим его в отдельном потоке.

> **Нужно знать: потоки.** `threading.Thread(target=f, daemon=True).start()` запускает функцию `f` параллельно с основной программой. `threading.Event()` — флаг: один поток делает `stop.set()`, другой ждёт `stop.wait(10)` (10 секунд, но просыпается сразу, если флаг поставили). `daemon=True` — поток не помешает программе завершиться.

> Соединение psycopg нельзя одновременно использовать из двух потоков. У писателя **своё** соединение.

Все изменения писатель делает только на тестовой трассе из урока 3.

```python
import random
import threading
from datetime import date, timedelta

RACE_SIZE = 20          # заездов в одной новой гонке
BATCH = 20              # строк за одну операцию


def load_refs(conn) -> dict:
    return {
        "test_track": conn.execute(
            "SELECT track_id FROM track WHERE name = 'Lab09 Test Ring'").fetchone()[0],
        "drivers": [r[0] for r in conn.execute("SELECT driver_id FROM driver")],
        "cars": [r[0] for r in conn.execute("SELECT car_id FROM car")],
    }


def fmt_td(seconds: float) -> timedelta:
    return timedelta(seconds=round(seconds, 3))


def do_insert(conn, refs):
    """Новая гонка на тестовой трассе: свободная дата, свободные пилоты, все CHECK соблюдены."""
    track = refs["test_track"]
    used = {r[0] for r in conn.execute("SELECT race_date FROM race_entry WHERE track_id = %s", (track,))}
    race_date = next(date.today() - timedelta(days=k) for k in range(10_000)
                     if date.today() - timedelta(days=k) not in used)
    busy = {r[0] for r in conn.execute("SELECT driver_id FROM race_entry WHERE race_date = %s", (race_date,))}
    drivers = random.sample([d for d in refs["drivers"] if d not in busy], RACE_SIZE)
    cars = random.sample(refs["cars"], RACE_SIZE)

    laps, lap_s = 50, random.uniform(75, 95)
    results = []
    for driver, car in zip(drivers, cars):
        best = lap_s * random.uniform(0.98, 1.03)
        total = best * laps * random.uniform(1.03, 1.08)          # всегда >= best * laps
        results.append((driver, car, best, total))
    results.sort(key=lambda x: x[3])                              # место по общему времени

    rows = [(driver, car, track, "finished", grid, pos, fmt_td(best), fmt_td(total), race_date, laps)
            for pos, ((driver, car, best, total), grid) in
            enumerate(zip(results, random.sample(range(1, RACE_SIZE + 1), RACE_SIZE)), start=1)]
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO race_entry (driver_id, car_id, track_id, status, grid_position, finish_position,
                                    best_lap, total_time, race_date, laps_completed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, rows)


RECENT_TEST = """
SELECT driver_id, race_date FROM race_entry
WHERE track_id = %s AND status = 'finished' AND laps_completed > 1
ORDER BY random() LIMIT %s
"""


def do_delete(conn, refs):
    conn.execute(f"DELETE FROM race_entry WHERE (driver_id, race_date) IN ({RECENT_TEST})",
                 (refs["test_track"], BATCH))


def do_update(conn, refs):
    conn.execute(f"""
        UPDATE race_entry SET laps_completed = laps_completed - 1
        WHERE (driver_id, race_date) IN ({RECENT_TEST})""", (refs["test_track"], BATCH))


OPERATIONS = {"insert": do_insert, "delete": do_delete, "update": do_update}


def writer(scenario: str, stop: threading.Event, interval: int = 10) -> None:
    op = OPERATIONS[scenario]
    r = connect_redis()
    with connect_db() as conn:           # своё соединение
        refs = load_refs(conn)
        while not stop.wait(interval):   # ждём 10 с или сигнал остановки
            op(conn, refs)               # autocommit: изменение уже зафиксировано
            invalidate(r)                # и только потом сбрасываем кэш
            print(f"    [writer] {scenario}, кэш сброшен")
```

`timedelta` из Python psycopg передаёт как `interval`, `date` — как `date`, ничего форматировать не нужно.

> **Порядок сценариев важен.** `delete` и `update` работают с гонками, которые создал `insert`. Запускай сценарии в порядке `none → insert → update → delete` (так они и стоят в `main`, урок 8). Если запустить `delete` первым, ему нечего будет удалять: эксперимент пройдёт, но кэш будет сбрасываться впустую.

> `update` уменьшает число кругов у финишировавших. Все `CHECK` остаются верными: кругов по-прежнему ≥ 1, а `total_time >= best_lap * laps_completed` при уменьшении кругов только «выполняется сильнее». Изменение влияет на столбец `laps` в статистике, поэтому сбрасывать кэш нужно.

> Удаление строк из гонки оставляет «дыры» в местах (было 1, 2, 3, стало 1, 3). Никакое ограничение этого не запрещает, а для тестовой трассы это неважно. В настоящих данных так делать не стоит: для этого у тебя есть `pr_disqualify`, который сдвигает места.

> Выбор даты (`next(... if ... not in used)`) идёт от сегодняшнего дня назад до первой свободной даты на тестовой трассе. `chk_race_date` запрещает будущие даты, поэтому вперёд идти нельзя.

### Практика

1. Запусти писателя на 30 секунд отдельно (`stop = threading.Event(); threading.Thread(target=writer, args=("insert", stop), daemon=True).start(); time.sleep(31); stop.set()`) и проверь в `psql`, что на тестовой трассе появилось 3 гонки по 20 пилотов (`SELECT race_date, count(*) FROM race_entry WHERE track_id = ... GROUP BY 1`).
2. (*) Сделай вариант `do_update`, который меняет только `grid_position` (переставляет двух пилотов на старте). Влияет ли это на `STATS_SQL`? Нужно ли тогда сбрасывать кэш? И как переставить две позиции, не нарушив `uq_race_entry_grid_position` посередине?

## Урок 8. Цикл замеров

Основной цикл: каждые 5 секунд выполняем запрос обоими способами и записываем время в CSV.

```python
import argparse
import csv
from datetime import datetime

INTERVAL = 5


def run(scenario: str, duration: int, out_path: str) -> None:
    r = connect_redis()
    r.delete(CACHE_KEY)                          # каждый сценарий начинаем с пустого кэша

    stop = threading.Event()
    if scenario != "none":
        threading.Thread(target=writer, args=(scenario, stop), daemon=True).start()

    new_file = not os.path.exists(out_path)
    with connect_db() as conn, open(out_path, "a", newline="") as f:
        out = csv.writer(f)
        if new_file:
            out.writerow(["scenario", "tick", "time", "mode", "ms", "hit"])

        t_start = time.monotonic()
        tick = 0
        while time.monotonic() - t_start < duration:
            tick_start = time.monotonic()
            now = datetime.now().isoformat(timespec="seconds")

            _, db_ms = query_db(conn)
            _, cache_ms, hit = query_cached(conn, r)

            out.writerow([scenario, tick, now, "db", f"{db_ms:.3f}", ""])
            out.writerow([scenario, tick, now, "redis", f"{cache_ms:.3f}", int(hit)])
            f.flush()
            print(f"[{scenario}] #{tick:3d}  db {db_ms:8.2f} мс   redis {cache_ms:8.2f} мс  {'HIT' if hit else 'MISS'}")

            tick += 1
            time.sleep(max(0.0, INTERVAL - (time.monotonic() - tick_start)))

    stop.set()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=["none", "insert", "delete", "update", "all"], default="all")
    p.add_argument("--duration", type=int, default=120, help="секунд на сценарий")
    p.add_argument("--out", default="results.csv")
    args = p.parse_args()

    scenarios = ["none", "insert", "update", "delete"] if args.scenario == "all" else [args.scenario]
    for s in scenarios:
        run(s, args.duration, args.out)


if __name__ == "__main__":
    main()
```

```bash
export PGHOST=localhost PGPORT=5433 PGDATABASE=study PGUSER=postgres PGPASSWORD=postgres
rm -f results.csv
python lab09.py --scenario all --duration 120
```

Восемь минут: четыре сценария по две минуты, в каждом 24 замера обоими способами.

| Решение | Почему |
|---|---|
| оба способа в одном такте, друг за другом | условия одинаковые: та же нагрузка писателя, тот же момент |
| `time.sleep(INTERVAL - затраченное)` | такт ровно 5 секунд, а не «5 секунд плюс время запросов» |
| пустой кэш в начале сценария | сценарии не влияют друг на друга |
| запись в CSV | графики строятся отдельно, замер можно повторить |
| `f.flush()` | данные не потеряются при Ctrl+C |

> Первый замер каждого сценария через кэш всегда miss: кэш пустой. Это честно, не выбрасывай его.

> Прямой запрос стоит **перед** запросом через кэш. При miss кэш выполняет тот же SQL по уже прогретым страницам. Это слегка в пользу кэша; если хочешь строже, меняй порядок через такт.

### Практика

1. Запусти сценарий `none` на 30 секунд: сколько hit и сколько miss?
2. Запусти `insert` на 30 секунд. Как чередуются hit и miss? Объясни почему.

## Урок 9. Графики

Пункт 3.3: сформировать графики зависимости. Строим время каждого запроса по тактам для всех сценариев и средние значения.

`plot.py`:

```python
import csv
from collections import defaultdict
from statistics import mean, median

import matplotlib.pyplot as plt

SCENARIOS = ["none", "insert", "update", "delete"]
TITLES = {
    "none": "Без изменений",
    "insert": "INSERT каждые 10 с",
    "delete": "DELETE каждые 10 с",
    "update": "UPDATE каждые 10 с",
}

data = defaultdict(lambda: defaultdict(list))      # data[scenario][mode] = [(tick, ms, hit)]
with open("results.csv", newline="") as f:
    for row in csv.DictReader(f):
        data[row["scenario"]][row["mode"]].append(
            (int(row["tick"]), float(row["ms"]), row["hit"] == "1"))

# 1. Время по тактам
fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharey=True)
for ax, s in zip(axes.flat, SCENARIOS):
    db = data[s]["db"]
    rd = data[s]["redis"]
    ax.plot([t for t, _, _ in db], [ms for _, ms, _ in db], marker="o", markersize=3, label="PostgreSQL")
    ax.plot([t for t, _, _ in rd], [ms for _, ms, _ in rd], marker="o", markersize=3, label="через Redis")
    misses = [(t, ms) for t, ms, hit in rd if not hit]
    ax.scatter([t for t, _ in misses], [ms for _, ms in misses], marker="x", s=60, label="промах кэша", zorder=3)
    ax.set_title(TITLES[s])
    ax.set_xlabel("такт (5 с)")
    ax.set_ylabel("время, мс")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
axes.flat[0].legend()
fig.suptitle("Время статистического запроса: PostgreSQL против кэша Redis")
fig.tight_layout()
fig.savefig("latency_by_tick.png", dpi=150)

# 2. Средние и медианы
fig, ax = plt.subplots(figsize=(10, 5))
width = 0.2
x = range(len(SCENARIOS))
for i, (mode, stat, label) in enumerate([
        ("db", mean, "PostgreSQL, среднее"),
        ("redis", mean, "Redis, среднее"),
        ("db", median, "PostgreSQL, медиана"),
        ("redis", median, "Redis, медиана")]):
    values = [stat([ms for _, ms, _ in data[s][mode]]) for s in SCENARIOS]
    ax.bar([xi + (i - 1.5) * width for xi in x], values, width, label=label)
ax.set_xticks(list(x))
ax.set_xticklabels([TITLES[s] for s in SCENARIOS])
ax.set_ylabel("время, мс")
ax.set_yscale("log")
ax.legend()
ax.grid(True, axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig("latency_summary.png", dpi=150)

# 3. Таблица в консоль
print(f"{'сценарий':<22}{'БД ср.':>10}{'Redis ср.':>12}{'ускорение':>12}{'hit-rate':>10}")
for s in SCENARIOS:
    db = mean(ms for _, ms, _ in data[s]["db"])
    rd = mean(ms for _, ms, _ in data[s]["redis"])
    hits = [h for _, _, h in data[s]["redis"]]
    print(f"{TITLES[s]:<22}{db:>10.2f}{rd:>12.2f}{db / rd:>11.1f}x{sum(hits) / len(hits):>9.0%}")
```

```bash
python plot.py
```

> Логарифмическая шкала обязательна: Redis отвечает за 0,3 мс, PostgreSQL за 70 мс. На обычной шкале линия Redis слипнется с нулём.

> Медиана рядом со средним показывает, насколько результат искажают выбросы. У кэша при изменениях среднее тянут вверх промахи, а медиана может оставаться маленькой.

### Практика

1. Построй графики по своему `results.csv` и вставь их в отчёт.
2. (*) Добавь гистограмму времени для Redis в сценарии `insert`. Должно получиться два «горба» — hit и miss.

## Урок 10. Анализ результатов

Разберём, что должно получиться и почему. Цифры у тебя будут свои, важно соотношение.

**Без изменений.** Первый запрос через кэш — miss, дальше все hit до истечения TTL (60 с, то есть каждый 12-й такт снова miss). Redis быстрее в десятки–сотни раз.

**С изменениями каждые 10 секунд.** Запросы каждые 5 секунд, сброс кэша каждые 10. Примерно каждый второй запрос через кэш — miss:

```
время:  0     5     10    15    20    25    30
запрос: MISS  HIT   MISS  HIT   MISS  HIT   MISS
запись:             ↑сброс      ↑сброс      ↑сброс
```

Среднее время через кэш ≈ (miss + hit) / 2 ≈ половина времени БД. Ускорение около 2 раз, а не сотни.

Главный вывод для отчёта:

> **Эффект кэша определяется отношением чтений к изменениям.** Если данные меняются чаще, чем их читают, кэш почти бесполезен: почти каждое чтение — промах. Кэш выгоден, когда на одно изменение приходится много чтений.

Если читать раз в секунду, а писать раз в 10 секунд, hit-rate будет около 90%. Это легко проверить, поменяв `INTERVAL`.

Разница между INSERT, DELETE и UPDATE для кэша почти не видна: любое изменение сбрасывает ключ целиком. Разница проявляется в прямых запросах:

| Сценарий | Что видно на графике PostgreSQL |
|---|---|
| без изменений | ровная линия |
| INSERT | на 54 тысячах строк +20 строк раз в 10 секунд почти незаметно |
| DELETE | колебания: удалённые строки остаются «мёртвыми» до `VACUUM`, их приходится просматривать |
| UPDATE | похоже на DELETE: в PostgreSQL `UPDATE` = новая версия строки + мёртвая старая |

> Если различия между INSERT/DELETE/UPDATE в прямых запросах не видны, это честный результат. Не подгоняй выводы: так и напиши, что 50 строк раз в 10 секунд на сотнях тысяч — ниже уровня шума.

Чек-лист выводов:

- во сколько раз hit быстрее прямого запроса;
- hit-rate в каждом сценарии и почему он такой;
- как изменения данных влияют на среднее время через кэш;
- влияет ли тип изменения на время прямых запросов;
- при каком соотношении чтений и записей кэш оправдан.

### Практика

1. Сравни результаты со своей гипотезой из урока 0.
2. Повтори эксперимент с `INTERVAL = 1` и `--duration 60`. Как изменился hit-rate в сценариях с изменениями?

## Урок 11. Инвалидация по событию из базы

Явный сброс работает, только если изменения делает наше приложение. Изменение из `psql` или другого сервиса кэш не заметит до истечения TTL. Решение: пусть база сама сообщает об изменениях через `LISTEN`/`NOTIFY`.

Триггеры на таблицы, от которых зависит статистика:

```sql
CREATE OR REPLACE FUNCTION notify_stats_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('stats_changed', TG_TABLE_NAME);
    RETURN NULL;
END $$;

CREATE TRIGGER trg_race_entry_stats
AFTER INSERT OR UPDATE OR DELETE ON race_entry
FOR EACH STATEMENT EXECUTE FUNCTION notify_stats_changed();

CREATE TRIGGER trg_driver_stats
AFTER UPDATE OR DELETE ON driver
FOR EACH STATEMENT EXECUTE FUNCTION notify_stats_changed();

CREATE TRIGGER trg_car_stats
AFTER UPDATE OR DELETE ON car
FOR EACH STATEMENT EXECUTE FUNCTION notify_stats_changed();
```

`FOR EACH STATEMENT` — одно уведомление на весь оператор, а не на каждую строку. `NOTIFY` доставляется после `COMMIT`, так что порядок «сначала коммит, потом сброс» соблюдается сам. Одинаковые уведомления внутри одной транзакции PostgreSQL склеивает в одно.

> Триггеры на `driver` и `car` тоже нужны: переименование пилота или перевод машины в другую команду меняет результат статистики, хотя `race_entry` не трогается.

> Это уже **третий** триггер на `race_entry` после `tr_race_entry_audit` из лабы 3 (если он есть). Порядок срабатывания `AFTER`-триггеров одного события — по алфавиту имён; здесь он ни на что не влияет.

> `pr_disqualify` теперь тоже сбрасывает кэш автоматически: он делает `UPDATE race_entry`, триггер шлёт уведомление. Явный сброс (урок 6) этого бы не заметил.

Слушатель в Python:

```python
def listener(stop: threading.Event) -> None:
    r = connect_redis()
    with connect_db() as conn:                          # autocommit обязателен для notifies()
        conn.execute("LISTEN stats_changed")
        while not stop.is_set():
            for note in conn.notifies(timeout=1.0):     # уведомления за ближайшую секунду
                invalidate(r)
                print(f"    [listener] изменение в {note.payload}, кэш сброшен")
```

> `conn.notifies()` — генератор. Без `timeout` он ждёт вечно, и поток не остановится по `stop`. С `timeout=1.0` генератор завершается после секунды тишины, внешний `while` проверяет флаг и подписывается снова. Параметр `timeout` появился в psycopg 3.2; на старой версии обнови пакет.

Чтобы попробовать: запусти слушатель в потоке, а из писателя убери `invalidate(r)`. Затем поменяй данные из `psql` и убедись, что кэш сбрасывается и без участия приложения.

Подробнее: [NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html).

### Практика

1. Подключи слушатель вместо явного сброса и повтори сценарий `insert`. Результаты должны совпасть с явным сбросом.
2. (*) Вызови `pr_disqualify` из `psql` (в настоящих данных, внутри `BEGIN ... ROLLBACK`, затем повторно с `COMMIT` на тестовой трассе) и убедись, что слушатель сбросил кэш без участия приложения.

---

# Итог: готовое приложение

```
lab09/
├── docker-compose.yml     ← Redis
├── seed.sql               ← тестовая трасса для писателя
├── lab09.py               ← замеры
├── plot.py                ← графики
├── results.csv            ← появится после запуска
├── latency_by_tick.png
└── latency_summary.png
```

`lab09.py` целиком:

```python
"""Сравнение времени статистического запроса: PostgreSQL напрямую и через кэш Redis."""
import argparse
import csv
import json
import os
import random
import threading
import time
from datetime import date, datetime, timedelta

import psycopg
import redis

STATS_SQL = """
SELECT d.full_name AS driver, d.country,
       count(*) AS starts,
       count(*) FILTER (WHERE re.finish_position = 1) AS wins,
       count(*) FILTER (WHERE re.finish_position <= 3) AS podiums,
       sum(coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[re.finish_position], 0)) AS points,
       sum(re.laps_completed) AS laps,
       min(re.best_lap) AS best_lap,
       count(DISTINCT c.team_id) AS teams
FROM race_entry re
JOIN driver d ON d.driver_id = re.driver_id
JOIN car c    ON c.car_id    = re.car_id
GROUP BY d.driver_id, d.full_name, d.country
ORDER BY points DESC
LIMIT 10
"""
CACHE_KEY = "stats:all_time:v1"
CACHE_TTL = 60
INTERVAL = 5
WRITE_INTERVAL = 10
RACE_SIZE = 20
BATCH = 20
RECENT_TEST = """
SELECT driver_id, race_date FROM race_entry
WHERE track_id = %s AND status = 'finished' AND laps_completed > 1
ORDER BY random() LIMIT %s
"""


def connect_db():
    return psycopg.connect(autocommit=True)


def connect_redis():
    return redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)


def query_db(conn):
    t0 = time.perf_counter()
    rows = conn.execute(STATS_SQL).fetchall()
    return rows, (time.perf_counter() - t0) * 1000


def query_cached(conn, r):
    t0 = time.perf_counter()
    raw = r.get(CACHE_KEY)
    if raw is not None:
        rows, hit = json.loads(raw), True
    else:
        rows = [list(row) for row in conn.execute(STATS_SQL).fetchall()]
        r.set(CACHE_KEY, json.dumps(rows, default=str), ex=CACHE_TTL)
        hit = False
    return rows, (time.perf_counter() - t0) * 1000, hit


def invalidate(r):
    r.delete(CACHE_KEY)


def load_refs(conn):
    return {"test_track": conn.execute(
                "SELECT track_id FROM track WHERE name = 'Lab09 Test Ring'").fetchone()[0],
            "drivers": [r[0] for r in conn.execute("SELECT driver_id FROM driver")],
            "cars": [r[0] for r in conn.execute("SELECT car_id FROM car")]}


def do_insert(conn, refs):
    track = refs["test_track"]
    used = {r[0] for r in conn.execute("SELECT race_date FROM race_entry WHERE track_id = %s", (track,))}
    race_date = next(date.today() - timedelta(days=k) for k in range(10_000)
                     if date.today() - timedelta(days=k) not in used)
    busy = {r[0] for r in conn.execute("SELECT driver_id FROM race_entry WHERE race_date = %s", (race_date,))}
    drivers = random.sample([d for d in refs["drivers"] if d not in busy], RACE_SIZE)
    cars = random.sample(refs["cars"], RACE_SIZE)
    laps, lap_s = 50, random.uniform(75, 95)
    results = []
    for driver, car in zip(drivers, cars):
        best = lap_s * random.uniform(0.98, 1.03)
        results.append((driver, car, best, best * laps * random.uniform(1.03, 1.08)))
    results.sort(key=lambda x: x[3])
    grids = random.sample(range(1, RACE_SIZE + 1), RACE_SIZE)
    rows = [(d, c, track, "finished", g, pos, timedelta(seconds=round(b, 3)),
             timedelta(seconds=round(t, 3)), race_date, laps)
            for pos, ((d, c, b, t), g) in enumerate(zip(results, grids), start=1)]
    with conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO race_entry (driver_id, car_id, track_id, status, grid_position, finish_position,
                                    best_lap, total_time, race_date, laps_completed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", rows)


def do_delete(conn, refs):
    conn.execute(f"DELETE FROM race_entry WHERE (driver_id, race_date) IN ({RECENT_TEST})",
                 (refs["test_track"], BATCH))


def do_update(conn, refs):
    conn.execute(f"""
        UPDATE race_entry SET laps_completed = laps_completed - 1
        WHERE (driver_id, race_date) IN ({RECENT_TEST})""", (refs["test_track"], BATCH))


OPERATIONS = {"insert": do_insert, "delete": do_delete, "update": do_update}


def writer(scenario, stop):
    op = OPERATIONS[scenario]
    r = connect_redis()
    with connect_db() as conn:
        refs = load_refs(conn)
        while not stop.wait(WRITE_INTERVAL):
            op(conn, refs)
            invalidate(r)
            print(f"    [writer] {scenario}, кэш сброшен")


def run(scenario, duration, out_path):
    r = connect_redis()
    r.delete(CACHE_KEY)
    stop = threading.Event()
    if scenario != "none":
        threading.Thread(target=writer, args=(scenario, stop), daemon=True).start()

    new_file = not os.path.exists(out_path)
    with connect_db() as conn, open(out_path, "a", newline="") as f:
        out = csv.writer(f)
        if new_file:
            out.writerow(["scenario", "tick", "time", "mode", "ms", "hit"])
        t_start, tick = time.monotonic(), 0
        while time.monotonic() - t_start < duration:
            tick_start = time.monotonic()
            now = datetime.now().isoformat(timespec="seconds")
            _, db_ms = query_db(conn)
            _, cache_ms, hit = query_cached(conn, r)
            out.writerow([scenario, tick, now, "db", f"{db_ms:.3f}", ""])
            out.writerow([scenario, tick, now, "redis", f"{cache_ms:.3f}", int(hit)])
            f.flush()
            print(f"[{scenario}] #{tick:3d}  db {db_ms:8.2f} мс   redis {cache_ms:8.2f} мс  {'HIT' if hit else 'MISS'}")
            tick += 1
            time.sleep(max(0.0, INTERVAL - (time.monotonic() - tick_start)))
    stop.set()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=["none", "insert", "delete", "update", "all"], default="all")
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--out", default="results.csv")
    args = p.parse_args()
    for s in (["none", "insert", "update", "delete"] if args.scenario == "all" else [args.scenario]):
        run(s, args.duration, args.out)


if __name__ == "__main__":
    main()
```

`plot.py` — из урока 9 без изменений.

Порядок сдачи:

```bash
docker compose up -d
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d study -f seed.sql
rm -f results.csv
python lab09.py --scenario all --duration 120
python plot.py
```

# Финальное задание

Сделай второе исследование на другом запросе, не подглядывая в уроки:

- Статистика: карточка трассы (число гонок, рекорд круга с автором и датой, пилот с наибольшим числом побед, средний процент сходов). Кэш — **хеш** Redis, где поле — `track_id`, а значение — JSON карточки (`HSET stats:tracks <id> <json>`).
- Изменения: каждые 10 секунд добавляется гонка на одной из трёх тестовых трасс. Сбрасывай только поле затронутой трассы (`HDEL`), а не весь хеш. Запросы каждые 5 секунд идут по случайной трассе из десятка «популярных» и трёх тестовых.
- Сравни три варианта кэша: только TTL 30 с, явный сброс всего хеша, точечный сброс поля по `NOTIFY` с `track_id` в payload (`FOR EACH ROW`-триггер). Для «только TTL» дополнительно измеряй, насколько результат из кэша отличается от свежего.
- Графики времени и hit-rate для всех трёх вариантов, вывод: какой вариант когда выбирать.

# Шпаргалка

```bash
docker compose up -d
docker exec -it redis redis-cli --raw
SET k v EX 60   GET k   DEL k   TTL k   EXISTS k   SCAN 0 MATCH stats:*   INFO stats   FLUSHDB
```

```python
r = redis.Redis(host="localhost", port=6379, decode_responses=True)
r.set(key, json.dumps(obj, default=str), ex=60)
obj = json.loads(raw) if (raw := r.get(key)) is not None else None
r.delete(key)     r.ttl(key)     r.hset(h, field, value)     r.hget(h, field)     r.hdel(h, field)

t0 = time.perf_counter(); ...; ms = (time.perf_counter() - t0) * 1000

stop = threading.Event()
threading.Thread(target=f, args=(...), daemon=True).start()
while not stop.wait(10): ...      # каждые 10 с до stop.set()

conn = psycopg.connect(autocommit=True)
conn.execute("LISTEN ch")
while not stop.is_set():
    for n in conn.notifies(timeout=1.0): ...
```

```sql
DELETE FROM race_entry WHERE (driver_id, race_date) IN (SELECT driver_id, race_date ... LIMIT 20);   -- составной ключ
coalesce((ARRAY[25,18,15,12,10,8,6,4,2,1])[finish_position], 0)                                    -- очки
SELECT pg_notify('ch', 'payload');
CREATE TRIGGER t AFTER INSERT OR UPDATE OR DELETE ON tbl FOR EACH STATEMENT EXECUTE FUNCTION f();
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;
```

Порядок при записи: изменение в БД → `COMMIT` → `DEL` ключа в Redis.

# Источники и что почитать дальше

**Официальная документация**
- [Redis data types](https://redis.io/docs/latest/develop/data-types/) — строки, хеши, списки, множества: что выбрать для кэша.
- [SET](https://redis.io/docs/latest/commands/set/) — параметры `EX`, `PX`, `NX`, `XX`.
- [Redis patterns](https://redis.io/docs/latest/develop/use/patterns/) — типовые приёмы, включая кэширование.
- [redis-py guide](https://redis.io/docs/latest/develop/clients/redis-py/) — подключение и основные операции из Python.
- [redis-py reference](https://redis.readthedocs.io/en/stable/) — полный API библиотеки.
- [PostgreSQL: NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html) — как работают уведомления и когда они доставляются.
- [PostgreSQL: Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html) — «кэш внутри базы» для сравнения с Redis.
- [psycopg 3: Basic usage](https://www.psycopg.org/psycopg3/docs/basic/usage.html) — соединения и `autocommit`.
- [matplotlib: User guide](https://matplotlib.org/stable/users/index.html) — графики, подписи, логарифмическая шкала.

**Курсы**
- [Docker: Get started](https://docs.docker.com/get-started/) — если нужно подтянуть Docker.
