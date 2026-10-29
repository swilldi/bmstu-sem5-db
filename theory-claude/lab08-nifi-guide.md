# ETL на Apache NiFi (лабораторная 8)

Материал к лабораторной 8 «Использование ETL инструментов на примере NiFi». Строим конвейер: генератор раз в 5 минут кладёт в папку файл с результатами новой гонки, NiFi забирает его, проверяет, приводит к JSON, разбивает на записи и вставляет в таблицу `race_entry`. Попутно ведём журнал загрузок и отсекаем плохие файлы. Схема автогонок из лабы 1, база `study` в контейнере `study-pg` (порт 5433).

В конце ты сможешь:
- запустить NiFi 2 в Docker и подключить его к PostgreSQL;
- собрать поток из процессоров `GetFile → ConvertRecord → SplitJson → PutDatabaseRecord → LogAttribute`;
- брать параметры из имени файла через Expression Language;
- логировать загрузки в таблицу и проверять входные файлы по маске и по JSON Schema, включая связанные правила вроде «финишировал ⇔ есть место и время».

Как проходить: по порядку. Код генератора набирай руками, поток в NiFi собирай сам, ориентируясь на описания настроек. После каждого урока поток должен работать, следующий урок его расширяет.

**Что нужно знать заранее**

- **Docker и Docker Compose** (большой раздел, по ходу не объясняется): образы, контейнеры, `docker compose up -d`, проброс портов и томов (`volumes`), `docker logs`. Если с этим слабо, сначала пройди [Docker: Get started](https://docs.docker.com/get-started/).
- **Python** на уровне лабы 6: генератор пишем на нём, к базе ходим через psycopg.
- **JSON** (лаба 5): массивы объектов.

> Задание называет процессоры `ConvertJSONToSQL` и `PutSQL`, но для NiFi 2.x велит заменить их на `PutDatabaseRecord`. Здесь всё под NiFi 2.12 (актуальная на момент написания), поэтому используем `PutDatabaseRecord`.

**Содержание**

- Часть I. Подготовка
  - [Урок 0. Как устроен NiFi](#урок-0-как-устроен-nifi)
  - [Урок 1. Генератор файлов](#урок-1-генератор-файлов)
  - [Урок 2. NiFi в Docker и драйвер PostgreSQL](#урок-2-nifi-в-docker-и-драйвер-postgresql)
- Часть II. Основной поток
  - [Урок 3. GetFile и первый поток](#урок-3-getfile-и-первый-поток)
  - [Урок 4. Атрибуты из имени файла](#урок-4-атрибуты-из-имени-файла)
  - [Урок 5. ConvertRecord: CSV и JSON в один формат](#урок-5-convertrecord-csv-и-json-в-один-формат)
  - [Урок 6. SplitJson](#урок-6-splitjson)
  - [Урок 7. PutDatabaseRecord: запись в базу](#урок-7-putdatabaserecord-запись-в-базу)
  - [Урок 8. Ошибки и LogAttribute](#урок-8-ошибки-и-logattribute)
- Часть III. Логирование и проверка
  - [Урок 9. Журнал загруженных файлов](#урок-9-журнал-загруженных-файлов)
  - [Урок 10. Проверка входных файлов](#урок-10-проверка-входных-файлов)
  - [Урок 11. Сохранение потока](#урок-11-сохранение-потока)
- [Итог: схема потока](#итог-схема-потока)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. Подготовка

## Урок 0. Как устроен NiFi

Прежде чем кликать, разберёмся в словаре. В NiFi всё строится из нескольких понятий.

| Понятие | Что это | Аналогия |
|---|---|---|
| **FlowFile** | единица данных: **содержимое** (байты файла) + **атрибуты** (словарь «ключ → строка») | письмо: текст + конверт с адресом |
| **Processor** | блок, который что-то делает с FlowFile: читает файл, конвертирует, пишет в базу | станок на конвейере |
| **Relationship** | выход процессора: `success`, `failure`, `invalid`... | развилка после станка |
| **Connection** | стрелка от relationship одного процессора к другому, внутри неё **очередь** | лента конвейера |
| **Controller Service** | общий ресурс для процессоров: пул соединений с БД, читатель/писатель форматов | электрощит, к которому подключены станки |
| **Process Group** | папка с частью потока | цех |
| **Provenance** | история каждого FlowFile: откуда пришёл, что с ним делали | журнал отслеживания посылки |

Главное правило: у каждого процессора **каждая** relationship должна быть либо подключена к другому процессору, либо помечена как завершённая (auto-terminate). Иначе процессор не запустится и покажет жёлтый треугольник.

Если соединить одну relationship с двумя процессорами, FlowFile **клонируется**: каждый получит свою копию. Этим мы воспользуемся для журнала в уроке 9.

Атрибуты, которые NiFi ставит всегда: `filename`, `path`, `uuid`. Процессоры добавляют свои, например `GetFile` пишет `absolute.path`, `SplitJson` — `fragment.index`, `fragment.count`.

Подробнее: [NiFi Getting Started](https://nifi.apache.org/docs/nifi-docs/html/getting-started.html), раздел «Terminology».

### Практика

1. Нарисуй на бумаге (или в любом редакторе) будущий поток: от папки с файлами до таблицы `race_entry`, с процессорами из задания и стрелками `success`/`failure`. Сравнишь со схемой в конце методички.

## Урок 1. Генератор файлов

Пункт 1 лабы: приложение раз в 5 минут создаёт файл с новыми строками для `race_entry`. Имя файла строится по маске.

У тебя это сложнее, чем «нагенерировать случайных строк»: на `race_entry` висят полтора десятка ограничений, и многие связывают строки между собой. Поэтому **один файл = одна гонка**: трасса, дата и полный протокол.

### Что генератор обязан соблюдать

| Правило | Откуда |
|---|---|
| пилот не едет две гонки в один день | `PRIMARY KEY (driver_id, race_date)` |
| в одной гонке машина, стартовая и финишная позиции не повторяются | `uq_race_entry_car`, `uq_race_entry_grid_position`, `uq_race_entry_finish_position` |
| `finished` ⇔ есть `finish_position` и `total_time` | `chk_finish_position`, `chk_total_time` |
| у `finished` есть `best_lap` и хотя бы 1 круг | `chk_best_lap`, `chk_laps_completed_finish` |
| у `dns` 0 кругов; 0 кругов ⇒ нет `best_lap` | `chk_laps_completed_dns`, `chk_best_lap_zero_laps` |
| у `dsq` нет `best_lap` | `chk_best_lap_dsq` |
| `total_time >= best_lap * laps_completed` | `chk_best_lap_cmp_total_time` |
| дата гонки не позже сегодняшней | `chk_race_date` |

### Маска имени

```
<id файла>__<таблица>__<дата>_<время>.<формат>
000042__race_entry__20261020_143000.json
```

| Часть | Пример | Зачем |
|---|---|---|
| id файла | `000042` | порядковый номер, 6 цифр, растёт с каждым файлом |
| таблица | `race_entry` | в какую таблицу грузить; NiFi возьмёт её из имени |
| дата и время | `20261020_143000` | когда сформирован файл (не путать с датой гонки внутри) |
| формат | `json` или `csv` | по нему NiFi выберет, как читать файл |

Разделитель частей — **двойное** подчёркивание `__`. Одинарное не подходит: оно уже есть внутри имени таблицы `race_entry`, и по нему имя не разобрать однозначно.

Регулярное выражение маски (понадобится в уроке 10):

```
^\d{6}__[a-z_]+__\d{8}_\d{6}\.(json|csv)$
```

### Код

```
lab-08/
├── generator/
│   └── generator.py
└── input/          ← сюда пишет генератор, отсюда читает NiFi
```

```bash
cd lab-08
python3 -m venv .venv && source .venv/bin/activate
pip install "psycopg[binary]"
```

`generator/generator.py`:

```python
"""Генератор файлов с результатами новых гонок для NiFi. Один файл = одна гонка."""
import argparse
import csv
import json
import os
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg

TABLE = "race_entry"
COLUMNS = ["driver_id", "car_id", "track_id", "status", "grid_position", "finish_position",
           "best_lap", "total_time", "race_date", "laps_completed"]


def fmt_interval(seconds: float | None) -> str | None:
    """Секунды → строка интервала PostgreSQL '01:32:15.123'."""
    if seconds is None:
        return None
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def load_refs(conn) -> dict:
    def ids(sql):
        return [r[0] for r in conn.execute(sql)]
    return {
        "drivers": ids("SELECT driver_id FROM driver"),
        "cars": ids("SELECT car_id FROM car"),
        "tracks": ids("SELECT track_id FROM track"),
    }


def pick_slot(conn, refs: dict, size: int) -> tuple[int, date, list[int], list[int]]:
    """Трасса и дата, где ещё нет гонки, и свободные в этот день пилоты и машины."""
    while True:
        track = random.choice(refs["tracks"])
        race_date = date.today() - timedelta(days=random.randint(0, 60))
        exists = conn.execute("SELECT 1 FROM race_entry WHERE track_id = %s AND race_date = %s LIMIT 1",
                              (track, race_date)).fetchone()
        if exists:
            continue
        busy = {r[0] for r in conn.execute(
            "SELECT driver_id FROM race_entry WHERE race_date = %s", (race_date,))}
        drivers = random.sample([d for d in refs["drivers"] if d not in busy], size)
        cars = random.sample(refs["cars"], size)
        return track, race_date, drivers, cars


def make_race(conn, refs: dict, size: int, bad: bool = False) -> list[dict]:
    track, race_date, drivers, cars = pick_slot(conn, refs, size)
    laps = random.randint(40, 75)
    lap_s = random.uniform(70, 110)                       # «темп» трассы, секунд на круг
    statuses = random.choices(["finished", "dnf", "dsq", "dns"], weights=[80, 14, 2, 4], k=size)

    rows = []
    for i, (driver, car, status) in enumerate(zip(drivers, cars, statuses), start=1):
        best = total = None
        if status == "finished":
            done = laps
            best = lap_s * random.uniform(0.98, 1.03)
            total = best * laps * random.uniform(1.03, 1.08)   # всегда >= best * laps
        elif status == "dnf":
            done = random.randint(1, laps - 1)
            best = lap_s * random.uniform(0.99, 1.05)
        elif status == "dsq":
            done = random.randint(1, laps)
        else:                                                   # dns
            done = 0
        rows.append({
            "driver_id": driver, "car_id": car, "track_id": track,
            "status": status, "grid_position": i, "finish_position": None,
            "best_lap": fmt_interval(best), "total_time": fmt_interval(total),
            "race_date": race_date.isoformat(), "laps_completed": done,
            "_total": total,                                    # служебное, для расстановки мест
        })

    finishers = sorted((r for r in rows if r["status"] == "finished"), key=lambda r: r["_total"])
    for pos, r in enumerate(finishers, start=1):
        r["finish_position"] = pos
    for r in rows:
        del r["_total"]

    if bad:                                    # испорченная запись для проверки валидации
        victim = finishers[0] if finishers else rows[0]
        victim["finish_position"] = None       # finished без места — нарушение chk_finish_position
    return rows


def next_file_id(state: Path) -> int:
    n = int(state.read_text()) + 1 if state.exists() else 1
    state.write_text(str(n))
    return n


def write_file(out_dir: Path, rows: list[dict], fmt: str, file_id: int) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{file_id:06d}__{TABLE}__{ts}.{fmt}"
    tmp = out_dir / f".{name}.tmp"                    # скрытый временный файл
    if fmt == "json":
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)                    # None превратится в пустую ячейку
    final = out_dir / name
    os.replace(tmp, final)                            # атомарное переименование
    return final


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="input")
    p.add_argument("--interval", type=int, default=300, help="секунд между файлами")
    p.add_argument("--size", type=int, default=20, help="пилотов в гонке")
    p.add_argument("--format", choices=["json", "csv", "mix"], default="mix")
    p.add_argument("--bad", type=float, default=0.0, help="доля испорченных файлов, 0..1")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state = out.parent / ".generator_state"

    with psycopg.connect() as conn:                   # PGHOST, PGPORT=5433, PGDATABASE=study ...
        refs = load_refs(conn)
        while True:
            fmt = random.choice(["json", "csv"]) if args.format == "mix" else args.format
            bad = random.random() < args.bad
            rows = make_race(conn, refs, args.size, bad=bad)
            path = write_file(out, rows, fmt, next_file_id(state))
            print(f"{datetime.now():%H:%M:%S}  {path.name}  гонка {rows[0]['race_date']}, "
                  f"трасса {rows[0]['track_id']}, {len(rows)} пилотов{', ИСПОРЧЕН' if bad else ''}")
            if args.once:
                break
            conn.rollback()                           # не держать транзакцию открытой между файлами
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
```

Запуск:

```bash
export PGHOST=localhost PGPORT=5433 PGDATABASE=study PGUSER=postgres PGPASSWORD=postgres
python generator/generator.py --once --format json
python generator/generator.py --once --format csv
ls input
```

Для отладки удобно `--interval 20`, для сдачи — по умолчанию 300 секунд (5 минут).

> **Почему генератор смотрит в базу перед каждым файлом.** Свободность пилота зависит от даты: тот, кто уже ехал гонку 12 октября, не может поехать ещё одну в тот же день (первичный ключ). Поэтому `pick_slot` для каждой гонки выбирает трассу и дату без гонки и исключает занятых в этот день пилотов.

> **Почему места расставляются после.** `finish_position` должен идти 1, 2, 3… только среди финишировавших и соответствовать времени. Сначала считаем время каждому, потом сортируем финишировавших по `total_time`.

> **Интервалы — строками.** `"01:32:15.123"` PostgreSQL сам превратит в `interval`. Формат `ЧЧ:ММ:СС.ммм` подходит и для JSON, и для CSV.

> **Почему временный файл и `os.replace`.** Если писать сразу в `input/000042__...json`, NiFi может забрать файл, записанный наполовину. `os.replace` переименовывает атомарно. Имя временного файла начинается с точки, а `GetFile` по умолчанию такие игнорирует (урок 3).

> Генератор не знает про файлы, которые уже лежат в `input`, но ещё не загружены NiFi. Если NiFi выключен, а генератор работает, две гонки в очереди теоретически могут попасть на одну дату с одним пилотом. Шанс мал, а если случится, ты увидишь в уроке 8, как NiFi сообщает о нарушении первичного ключа.

### Практика

1. Сгенерируй по файлу каждого формата и открой их. Проверь вручную на одной гонке все правила из таблицы выше.
2. (*) Добавь в генератор проверку собственного результата: функцию `check_race(rows)`, которая перед записью файла проверяет правила из таблицы и падает, если что-то нарушено. Запусти 100 раз с `--once` в цикле.

## Урок 2. NiFi в Docker и драйвер PostgreSQL

Пункт 2 лабы: установить NiFi. Через Docker это одна команда, а локальная установка требует Java 21 и ручной настройки.

### Драйвер

NiFi написан на Java и ходит в базы через JDBC. Драйвер PostgreSQL — отдельный `.jar`, его нужно положить рядом:

```bash
mkdir -p drivers error
curl -L -o drivers/postgresql-42.7.14.jar \
  https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar
```

(версию можно взять новее со [страницы загрузки](https://jdbc.postgresql.org/download/))

### docker-compose.yml

```yaml
services:
  nifi:
    image: apache/nifi:2.12.0
    container_name: nifi
    ports:
      - "8443:8443"
    environment:
      SINGLE_USER_CREDENTIALS_USERNAME: admin
      SINGLE_USER_CREDENTIALS_PASSWORD: nifi-admin-12345     # не короче 12 символов
    volumes:
      - ./input:/data/input
      - ./error:/data/error
      - ./drivers:/opt/nifi/drivers
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

```bash
docker compose up -d
docker logs -f nifi        # ждём строку "Started Application" или "NiFi has started", 1–2 минуты
```

Открой `https://localhost:8443/nifi`. Браузер предупредит о самоподписанном сертификате: это нормально для локального стенда, прими исключение. Войди как `admin` / `nifi-admin-12345`.

| Что | Почему так |
|---|---|
| `apache/nifi:2.12.0` | конкретная версия, а не `latest`: поток не сломается от обновления образа |
| порт `8443`, HTTPS | NiFi 2 по умолчанию работает только по HTTPS с логином |
| пароль ≥ 12 символов | иначе NiFi сгенерирует случайные логин и пароль и запишет их в лог |
| `./input:/data/input` | папка генератора видна внутри контейнера как `/data/input` |
| `host.docker.internal` | так контейнер NiFi достучится до порта 5433, на который проброшен твой `study-pg` |

> Твой PostgreSQL уже в Docker (`study-pg`) и опубликован на хост как `5433`. Официальный образ `postgres` принимает подключения по сети с паролем, поэтому дополнительно ничего настраивать не нужно: NiFi ходит на `host.docker.internal:5433`, как на любой порт компьютера.

> Можно и без проброса через хост: добавить сервис `nifi` прямо в `docker-compose.yml` проекта рядом с `db`. Тогда адрес базы — `db:5432` (имя сервиса и внутренний порт). Но держать NiFi отдельным compose-файлом в папке лабы проще: он не перезапускается вместе с базой.

> На Linux контейнер NiFi работает от пользователя с uid 1000. Если `GetFile` не может удалить файл из `input`, дай права: `chmod 777 input error`.

### Практика

1. Подними NiFi, войди в интерфейс. Найди в логах (`docker logs nifi | grep -i password`) строку о пользователе и убедись, что NiFi взял твои логин и пароль, а не сгенерировал свои.
2. Проверь, что контейнер видит базу: `docker exec nifi bash -c "cat < /dev/tcp/host.docker.internal/5433 && echo ok"` (команда может зависнуть на секунду — это нормально, важно отсутствие ошибки «Connection refused»).

# Часть II. Основной поток

## Урок 3. GetFile и первый поток

Собираем минимальный поток: забрать файл из папки и посмотреть на него. Так ты освоишь интерфейс до того, как появятся базы и форматы.

### Добавить процессор

1. В верхней панели перетащи значок **Processor** на холст.
2. В поиске набери `GetFile`, выбери, **Add**.
3. Двойной клик по процессору (или правый клик → **Configure**) → вкладка **Properties**.

Настройки `GetFile`:

| Свойство | Значение | Зачем |
|---|---|---|
| Input Directory | `/data/input` | путь **внутри контейнера** |
| File Filter | `[^\.].*` (по умолчанию) | пропускает файлы, начинающиеся с точки, то есть наши `.tmp` |
| Keep Source File | `false` | забрать файл (удалить из папки), иначе он будет читаться снова и снова |
| Polling Interval | `30 sec` | как часто заглядывать в папку |

4. Добавь второй процессор `LogAttribute`. В его **Relationships** отметь `success` → **terminate**.
5. Наведи мышь на `GetFile`, потяни стрелку к `LogAttribute`, выбери relationship `success`, **Add**.

Получилось:

```
GetFile ──success──▶ LogAttribute
```

### Запустить и посмотреть

1. Правый клик по `GetFile` → **Start**. `LogAttribute` пока **не** запускай.
2. Сгенерируй файл: `python generator/generator.py --once`.
3. Через несколько секунд на стрелке появится «Queued 1». Файла в `input` больше нет: NiFi его забрал.
4. Правый клик по стрелке → **List Queue** → значок «i» (или «eye») у FlowFile. На вкладке **Attributes** видны `filename`, `absolute.path`, `file.lastModifiedTime`; на **Content** — содержимое файла.
5. Запусти `LogAttribute`. Очередь опустеет, а в логе NiFi появятся атрибуты:

```bash
docker exec nifi tail -n 40 /opt/nifi/nifi-current/logs/nifi-app.log
```

> Пока процессор-получатель остановлен, FlowFile копятся в очереди. Это главный способ отладки в NiFi: останови процессор после проблемного места и посмотри, что лежит в очереди.

> Если `GetFile` с жёлтым треугольником, наведи на него мышь: NiFi напишет, чего не хватает (чаще всего не подключена или не завершена какая-то relationship).

Подробнее: [NiFi User Guide](https://nifi.apache.org/docs/nifi-docs/html/user-guide.html), разделы «Adding Components to the Canvas» и «Queue Interaction».

### Практика

1. Поставь `Keep Source File = true`, запусти и посмотри, что происходит с очередью через минуту. Объясни, почему так, и верни `false`.
2. Найди свой FlowFile в **Data Provenance** (меню в правом верхнем углу → Data Provenance) и посмотри его историю.

## Урок 4. Атрибуты из имени файла

Имя таблицы для вставки берём из имени файла: так один поток сможет грузить файлы в разные таблицы. Для этого служит `UpdateAttribute` и язык выражений NiFi (Expression Language, EL).

EL пишется в `${...}`: `${filename}` — значение атрибута, а дальше через двоеточие цепочка функций.

Добавь `UpdateAttribute` между `GetFile` и `LogAttribute` (удали старую стрелку: правый клик → **Delete**). В **Properties** нажми **+** и добавь свойства (каждое станет атрибутом FlowFile):

| Свойство (новый атрибут) | Значение | Результат для `000042__race_entry__20261020_143000.json` |
|---|---|---|
| `file.id` | `${filename:substringBefore('__')}` | `000042` |
| `target.table` | `${filename:substringAfter('__'):substringBeforeLast('__')}` | `race_entry` |
| `file.ts` | `${filename:substringAfterLast('__'):substringBefore('.')}` | `20261020_143000` |
| `file.format` | `${filename:substringAfterLast('.'):toLower()}` | `json` |

```
GetFile ──success──▶ UpdateAttribute ──success──▶ LogAttribute
```

Проверь через **List Queue**, что у FlowFile появились четыре новых атрибута.

| Функция EL | Что делает |
|---|---|
| `substringBefore('x')` | всё до первого `x` |
| `substringAfter('x')` | всё после первого `x` |
| `substringBeforeLast('x')`, `substringAfterLast('x')` | то же относительно последнего `x` |
| `toLower()`, `toUpper()` | регистр |
| `matches('regex')` | `true`, если вся строка подходит под регулярку |
| `equals('x')`, `endsWith('x')` | сравнения |
| `escapeJson()` | экранирует строку для вставки в JSON |
| `now():format('yyyy-MM-dd HH:mm:ss')` | текущее время |

> Почему `target.table` через `substringBeforeLast`, а не просто «второе поле»: в имени таблицы есть `_`, а между полями `__`. `substringAfter('__')` даёт `race_entry__20261020_143000.json`, а `substringBeforeLast('__')` отрезает хвост. Так работает для любой таблицы, даже с подчёркиваниями.

Подробнее: [Expression Language Guide](https://nifi.apache.org/docs/nifi-docs/html/expression-language-guide.html).

### Практика

1. Добавь атрибут `file.date` в формате `2026-10-20 14:30:00`, собранный из `file.ts` (подсказка: `toDate('yyyyMMdd_HHmmss'):format('yyyy-MM-dd HH:mm:ss')`).
2. Переименуй файл вручную в `000099__contract__20261020_120000.json` и проверь, что `target.table` стал `contract`.

## Урок 5. ConvertRecord: CSV и JSON в один формат

Дальше по потоку нужен только JSON. CSV-файлы переводим в JSON процессором `ConvertRecord`, а читателя выбираем по расширению.

### Record-процессоры

`ConvertRecord` не разбирает форматы сам. Он берёт **Record Reader** (читатель формата) и **Record Writer** (писатель формата). Это controller services, их создают один раз и используют в нескольких процессорах.

Для каждой записи нужна **схема**: какие поля и каких типов. Можно разрешить NiFi угадывать её (Infer Schema), но надёжнее задать явно. Тогда `"42"` в CSV станет числом, а лишние поля отбросятся. Схема пишется в формате Avro:

```json
{
  "type": "record",
  "name": "race_entry",
  "fields": [
    {"name": "driver_id",       "type": ["null", "long"]},
    {"name": "car_id",          "type": ["null", "long"]},
    {"name": "track_id",        "type": ["null", "long"]},
    {"name": "status",          "type": ["null", "string"]},
    {"name": "grid_position",   "type": ["null", "int"]},
    {"name": "finish_position", "type": ["null", "int"]},
    {"name": "best_lap",        "type": ["null", "string"]},
    {"name": "total_time",      "type": ["null", "string"]},
    {"name": "race_date",       "type": ["null", "string"]},
    {"name": "laps_completed",  "type": ["null", "int"]}
  ]
}
```

`["null", "long"]` означает «число или пусто». У `finish_position`, `best_lap`, `total_time` пустое значение законно (сход, дисквалификация), у остальных `null` разрешён намеренно: если поле пропало, конвертация не упадёт, а пропуск поймает проверка в уроке 10 с понятной ошибкой. Дату и интервалы оставляем строками: в `date` и `interval` их превратит база.

> В Avro нет типа «интервал PostgreSQL». Есть логический тип `duration`, но NiFi и драйвер не превратят его в `interval` сами. Строка `"01:32:15.123"` + `stringtype=unspecified` (урок 7) — самый простой рабочий путь.

### Controller services

Правый клик по пустому месту холста → **Controller Services** → **+**. Создай три сервиса:

**JsonTreeReader** (назови `RaceJsonReader`):

| Свойство | Значение |
|---|---|
| Schema Access Strategy | Use 'Schema Text' Property |
| Schema Text | Avro-схема выше |

**CSVReader** (назови `RaceCsvReader`):

| Свойство | Значение |
|---|---|
| Schema Access Strategy | Use 'Schema Text' Property |
| Schema Text | та же схема |
| Treat First Line as Header | true |

**JsonRecordSetWriter** (назови `JsonWriter`):

| Свойство | Значение |
|---|---|
| Schema Write Strategy | Do Not Write Schema |
| Schema Access Strategy | Inherit Record Schema |
| Output Grouping | Array |

Каждый сервис включи: значок с тремя точками → **Enable**. Выключенный сервис процессоры не видят.

> Пустые ячейки CSV (`finish_position` у сошедшего) должны прочитаться как `null`. Если CSV-ветка падает на пустой строке для числового поля, задай в CSVReader свойство `Null String`.

> Чтобы не копировать схему в несколько мест, её можно положить в **Parameter Context** (параметр `race_schema`) и в Schema Text написать `#{race_schema}`. Для лабы достаточно копирования, но если схема меняется, параметр избавит от рассинхронизации.

### Выбор читателя по расширению

`RouteOnAttribute` направляет FlowFile по условиям. Добавь его после `UpdateAttribute`:

| Свойство | Значение |
|---|---|
| Routing Strategy | Route to Property name |
| `json` (новое свойство) | `${file.format:equals('json')}` |
| `csv` (новое свойство) | `${file.format:equals('csv')}` |

У процессора появятся relationships `json`, `csv` и `unmatched`.

Два процессора `ConvertRecord`:

| | ConvertRecord (JSON) | ConvertRecord (CSV) |
|---|---|---|
| Record Reader | `RaceJsonReader` | `RaceCsvReader` |
| Record Writer | `JsonWriter` | `JsonWriter` |

```
UpdateAttribute ──▶ RouteOnAttribute ──json──▶ ConvertRecord (JSON) ──success──┐
                                    ├─csv───▶ ConvertRecord (CSV)  ──success──┤──▶ дальше (урок 6)
                                    └─unmatched──▶ LogAttribute
```

`failure` обоих `ConvertRecord` пока веди в `LogAttribute`.

После `ConvertRecord` у FlowFile есть атрибут `record.count` — число записей в файле. Пригодится в журнале.

> JSON → JSON через `ConvertRecord` тоже имеет смысл: запись проходит через схему, типы приводятся (`"42"` → `42`), лишние поля отбрасываются. На выходе обе ветки дают одинаковый JSON.

> Если поле есть в файле, но называется иначе (`bestLap` вместо `best_lap`), читатель со схемой его не узнает и поставит `null`. Имена в схеме должны совпадать с именами в файле.

Подробнее: [ConvertRecord](https://nifi.apache.org/components/org.apache.nifi.processors.standard.ConvertRecord/), [CSVReader](https://nifi.apache.org/components/org.apache.nifi.csv.CSVReader/), [JsonTreeReader](https://nifi.apache.org/components/org.apache.nifi.json.JsonTreeReader/).

### Практика

1. Пропусти через поток CSV-файл и сравни в **List Queue** содержимое до и после `ConvertRecord`.
2. (*) Если делал XML в генераторе: добавь ветку `xml` с `XMLReader` (Schema Text та же, `Expect Records as Array = true`).

## Урок 6. SplitJson

`SplitJson` разбивает JSON-массив на отдельные элементы: из протокола гонки на 20 пилотов получается 20 FlowFile по одному заезду.

| Свойство | Значение |
|---|---|
| JsonPath Expression | `$.*` |

`$` — корень документа, `.*` — все его элементы. Для массива верхнего уровня это каждый объект.

Relationships:

| Relationship | Что туда попадает |
|---|---|
| `split` | части, по одной записи |
| `original` | исходный файл целиком |
| `failure` | не JSON или путь не найден |

Обе ветки `ConvertRecord` → `success` веди в `SplitJson`. `original` пока заверши (terminate), `failure` — в `LogAttribute`.

Каждая часть получает атрибуты:

| Атрибут | Значение |
|---|---|
| `fragment.identifier` | общий id для всех частей одного файла |
| `fragment.index` | номер части, с 0 |
| `fragment.count` | сколько всего частей |
| `segment.original.filename` | имя исходного файла |

Атрибуты из урока 4 (`target.table`, `file.id`) у частей тоже остаются: дочерние FlowFile наследуют атрибуты родителя.

> **Для твоей таблицы это важный момент.** По заданию нужен `SplitJson`, и каждая запись вставляется отдельно. Если одна строка гонки упадёт (например, пилот уже ехал в этот день), остальные 19 вставятся, и в базе окажется **неполная гонка**. `PutDatabaseRecord` умеет вставлять весь массив одной транзакцией: тогда гонка загружается целиком или не загружается вовсе. На защите стоит сказать, что для протоколов гонок второй вариант правильнее, а `SplitJson` используется потому, что его требует задание.

### Практика

1. Пропусти файл на 20 строк и проверь в очереди после `SplitJson`, что частей 20, а `fragment.count = 20` у каждой.
2. Поставь `JsonPath Expression = $[0]` и посмотри, что получится. Верни `$.*`.

## Урок 7. PutDatabaseRecord: запись в базу

Вставляем каждую запись в таблицу.

### Пул соединений

Controller Services → **+** → **DBCPConnectionPool** (назови `StudyDB`):

| Свойство | Значение |
|---|---|
| Database Connection URL | `jdbc:postgresql://host.docker.internal:5433/study?stringtype=unspecified` |
| Database Driver Class Name | `org.postgresql.Driver` |
| Database Driver Locations | `/opt/nifi/drivers/postgresql-42.7.14.jar` |
| Database User | `postgres` |
| Password | `postgres` |

Включи сервис (**Enable**). Если драйвер не найден или база недоступна, ошибка появится сразу при включении или при первом запросе; смотри значок у сервиса и `nifi-app.log`.

> **`stringtype=unspecified` у тебя обязателен.** Драйвер по умолчанию отправляет строки с типом `varchar`, а столбцы `best_lap`, `total_time` — `interval`, `race_date` — `date`. PostgreSQL не приводит `varchar` к `interval` неявно и отвечает `column "best_lap" is of type interval but expression is of type character varying`. С этим параметром строка уходит без типа, и сервер сам разбирает `"00:01:31.452"` как интервал.

### Процессор

`PutDatabaseRecord` после `SplitJson` (relationship `split`):

| Свойство | Значение | Зачем |
|---|---|---|
| Record Reader | `RaceJsonReader` | каждая часть — один JSON-объект |
| Database Type | PostgreSQL | диалект SQL |
| Statement Type | INSERT | по заданию только новые записи |
| Database Connection Pooling Service | `StudyDB` | |
| Table Name | `${target.table}` | из имени файла (урок 4) |
| Translate Field Names | true | сопоставлять поля и столбцы без учёта регистра и `_` |
| Unmatched Field Behavior | Ignore Unmatched Fields | поле без столбца не мешает |
| Unmatched Column Behavior | Fail on Unmatched Columns | у тебя в записи есть **все** столбцы таблицы, так что строгий режим ничего не ломает и ловит опечатки в именах |
| Rollback On Failure | false | ошибочная запись уходит в `failure`, а не блокирует очередь |

Relationships: `success` — в `LogAttribute` (или terminate), `failure` и `retry` — в `LogAttribute` (урок 8).

Запусти всё и проверь в `psql`:

```sql
SELECT re.race_date, t.name AS track, re.finish_position AS pos, d.full_name,
       re.status, re.best_lap, re.total_time
FROM race_entry re
JOIN track t  USING (track_id)
JOIN driver d USING (driver_id)
WHERE re.race_date >= current_date - 60
ORDER BY re.race_date DESC, t.name, re.finish_position NULLS LAST
LIMIT 40;
```

> **Ключа-счётчика у `race_entry` нет.** Первичный ключ составной `(driver_id, race_date)`, и оба значения приходят в файле. Поэтому, в отличие от таблиц с `serial`, здесь нечего «оставлять базе»: все столбцы есть в записи.

> Ошибка `column "race_date" is of type date but expression is of type character varying` (или то же про `interval`) означает, что `stringtype=unspecified` не добавлен в URL или сервис не перевключён после правки.

> Если у тебя включён триггер аудита из лабы 3 (`tr_race_entry_audit`), каждая вставка NiFi запишется ещё и в `race_entry_audit`. Это хорошая проверка: `SELECT count(*) FROM race_entry_audit WHERE op = 'INSERT'` должен расти вместе с загрузкой.

Подробнее: [PutDatabaseRecord](https://nifi.apache.org/components/org.apache.nifi.processors.standard.PutDatabaseRecord/), [DBCPConnectionPool](https://nifi.apache.org/components/org.apache.nifi.dbcp.DBCPConnectionPool/), [pgJDBC: параметры подключения](https://jdbc.postgresql.org/documentation/use/).

### Практика

1. Запусти генератор с `--interval 20` и убедись, что в `race_entry` появляются гонки по 20 пилотов. Проверь одну гонку запросом из лабы 6 (протокол) — места идут подряд, время растёт с местом.
2. Сгенерируй файл, переименуй его в `...__contract__...` и пропусти. Что произошло и почему? (Подумай, что сделает `Fail on Unmatched Columns`, когда в записи есть поля, которых нет в `contract`, и какое из двух «Unmatched»-свойств тут срабатывает.)

## Урок 8. Ошибки и LogAttribute

Пункт 3.6: `LogAttribute` для логирования возможных ошибок. Настроим его так, чтобы по логу было понятно, что сломалось.

Сделай **отдельный** `LogAttribute` для ошибок (назови `Log errors`):

| Свойство | Значение |
|---|---|
| Log Level | error |
| Log Payload | true |
| Attributes to Log Regular Expression | `filename|file\..*|target\.table|fragment\..*|putdatabaserecord\.error|json\.validation\.errors` |
| Log Prefix | `LOAD-ERROR ` |

Подключи к нему `failure` (и `retry`) всех процессоров: `ConvertRecord`, `SplitJson`, `PutDatabaseRecord`, а также `unmatched` из `RouteOnAttribute`. `success` у `Log errors` — terminate.

Когда `PutDatabaseRecord` не может вставить запись, он пишет текст ошибки базы в атрибут `putdatabaserecord.error`. Он и попадёт в лог:

```bash
docker exec nifi grep "LOAD-ERROR" /opt/nifi/nifi-current/logs/nifi-app.log | tail
```

Проверь на ошибке первичного ключа — у твоей таблицы она возникает естественно. Сгенерируй файл, **скопируй** его до того, как NiFi заберёт, и подложи копию с другим именем:

```bash
python generator/generator.py --once --format json
cp input/000050__race_entry__*.json /tmp/race.json          # подставь своё имя
# дождись, пока NiFi загрузит оригинал, затем:
cp /tmp/race.json input/000051__race_entry__$(date +%Y%m%d_%H%M%S).json
```

Все 20 записей второй копии упадут с `duplicate key value violates unique constraint "pk_race_entry"`: пилоты уже ехали в этот день.

Для ошибки внешнего ключа поставь в файле вручную `"car_id": 999999`.

> `retry` у `PutDatabaseRecord` — ошибки, которые могут пройти при повторе (база временно недоступна). Их можно не в лог, а обратно на вход `PutDatabaseRecord`: NiFi повторит позже. В Relationships процессора для этого есть галочка **retry** с настройкой числа попыток.

> Не путай: `Log Payload = true` печатает содержимое FlowFile. Для записи из одной строки это удобно, для большого файла засорит лог.

Сохрани испорченные данные в папку `error` для разбора: добавь `PutFile` с `Directory = /data/error` и `Conflict Resolution Strategy = replace` после `Log errors` (или параллельно: подключи те же `failure` и к `PutFile`).

### Практика

1. Добейся каждой из ошибок и найди её в логе: битый JSON, повтор гонки (первичный ключ), несуществующая машина (внешний ключ), `"status": "dnf"` с непустым `finish_position` (`CHECK`). Для последней посмотри, какое именно ограничение назовёт база.
2. (*) Настрой на `PutDatabaseRecord` для `retry` повтор 3 раза с паузой, останови PostgreSQL на минуту и посмотри, как ведёт себя очередь.

# Часть III. Логирование и проверка

## Урок 9. Журнал загруженных файлов

Пункт 4 лабы: подход к логированию загруженных файлов на уровне NiFi. Лог в `nifi-app.log` хорош для отладки, но для отчёта нужен журнал, который можно запросить SQL: какой файл, сколько записей, когда, с каким результатом.

### Таблица журнала

```sql
CREATE TABLE nifi_load_log (
    id           serial PRIMARY KEY,
    file_id      varchar(20),
    file_name    text        NOT NULL,
    table_name   varchar(64),
    record_count int,
    status       varchar(20) NOT NULL,     -- received / invalid / failed_record
    message      text,
    logged_at    timestamp   NOT NULL DEFAULT now()
);
```

### Как записать в журнал из NiFi

Идея: клонировать FlowFile, заменить его содержимое на JSON-строку журнала, собранную из атрибутов, и вставить её тем же `PutDatabaseRecord` в другую таблицу.

1. От `success` обоих `ConvertRecord` протяни **вторую** стрелку к новому `ReplaceText` (назови `Build log: received`). FlowFile клонируется: одна копия идёт дальше в `SplitJson`, другая в журнал.

`ReplaceText`:

| Свойство | Значение |
|---|---|
| Replacement Strategy | Always Replace |
| Evaluation Mode | Entire text |
| Replacement Value | см. ниже |

```
{"file_id": "${file.id}", "file_name": "${filename:escapeJson()}", "table_name": "${target.table}", "record_count": ${record.count:replaceEmpty('null')}, "status": "received", "message": null}
```

2. Новый controller service `JsonTreeReader` (назови `LogJsonReader`) с `Schema Access Strategy = Infer Schema`: у журнала своя структура.

3. Новый `PutDatabaseRecord` (назови `Write log`): `Record Reader = LogJsonReader`, `Table Name = nifi_load_log`, `Statement Type = INSERT`, тот же пул `StudyDB`, `Unmatched Column Behavior = Ignore Unmatched Columns`.

4. Ошибки вставки записей тоже в журнал: от `failure` основного `PutDatabaseRecord` вторая стрелка к `ReplaceText` (`Build log: failed`):

```
{"file_id": "${file.id}", "file_name": "${segment.original.filename:escapeJson()}", "table_name": "${target.table}", "record_count": 1, "status": "failed_record", "message": "${putdatabaserecord.error:escapeJson()}"}
```

и оттуда в тот же `Write log`.

```
ConvertRecord ──success──┬──▶ SplitJson ──▶ ...
                         └──▶ ReplaceText (received) ──▶ Write log (PutDatabaseRecord → nifi_load_log)
PutDatabaseRecord ──failure──┬──▶ Log errors
                             └──▶ ReplaceText (failed)  ──▶ Write log
```

Запрос для отчёта:

```sql
SELECT l.file_name, l.record_count,
       l.record_count - coalesce(f.failed, 0) AS loaded,
       coalesce(f.failed, 0)                  AS failed,
       l.logged_at
FROM nifi_load_log l
LEFT JOIN (SELECT file_id, count(*) AS failed
           FROM nifi_load_log WHERE status = 'failed_record' GROUP BY file_id) f
       ON f.file_id = l.file_id
WHERE l.status = 'received'
ORDER BY l.logged_at DESC;
```

> `escapeJson()` обязателен для текста, который может содержать кавычки: сообщение об ошибке базы почти всегда содержит `"имя_столбца"`, и без экранирования JSON сломается, а с ним и запись в журнал.

> `record.count:replaceEmpty('null')` защищает от пустого атрибута: без него получится `"record_count": ,` и невалидный JSON.

> Почему журнал пишется после `ConvertRecord`, а не после `GetFile`: только после конвертации известно `record.count`. Файлы, которые не удалось даже прочитать, попадут в журнал через проверку в уроке 10 со статусом `invalid`.

Другие уровни логирования, которые стоит упомянуть в отчёте:

| Уровень | Где смотреть | Для чего |
|---|---|---|
| Таблица `nifi_load_log` | SQL | отчёт по файлам и ошибкам |
| `LogAttribute` → `nifi-app.log` | `docker exec nifi tail ...` | отладка, детали ошибок |
| Data Provenance | меню NiFi | путь каждого FlowFile, содержимое на любом шаге |
| Bulletins | значок у процессора, Bulletin Board | ошибки процессоров в реальном времени |

### Практика

1. Добейся ситуации, когда в журнале у одного файла `loaded = 19, failed = 1`, и покажи её запросом выше.
2. (*) Добавь статус `loaded`: после основного `PutDatabaseRecord` (`success`) поставь `MergeContent` с `Merge Strategy = Defragment` (он соберёт части одного файла по `fragment.identifier`) и уже после него пиши в журнал «файл полностью обработан».

## Урок 10. Проверка входных файлов

Пункт 5 лабы: подход к проверке входных файлов. Проверяем на двух уровнях: имя файла (маска) и содержимое (структура и значения).

### Уровень 1. Маска имени

В начало потока, сразу после `GetFile`, поставь `RouteOnAttribute` (назови `Check name`):

| Свойство | Значение |
|---|---|
| Routing Strategy | Route to Property name |
| `valid` | `${filename:matches('^\d{6}__[a-z_]+__\d{8}_\d{6}\.(json|csv)$')}` |

`valid` → `UpdateAttribute` (урок 4). `unmatched` → `Log errors`, `PutFile` в `/data/error` и журнал со статусом `invalid` через ещё один `ReplaceText`:

```
{"file_id": null, "file_name": "${filename:escapeJson()}", "table_name": null, "record_count": null, "status": "invalid", "message": "Имя файла не соответствует маске"}
```

> Можно и проще: прописать регулярку прямо в `File Filter` у `GetFile`, тогда неподходящие файлы NiFi просто не тронет. Но тогда они тихо копятся в папке, и о проблеме никто не узнает. Через `RouteOnAttribute` плохой файл попадает в журнал и в `error`.

### Уровень 2. Содержимое по JSON Schema

После `ConvertRecord` содержимое всегда JSON-массив, его проверяем `ValidateJson`. Ставим между `ConvertRecord` и `SplitJson`:

| Свойство | Значение |
|---|---|
| Schema Access Strategy | JSON Schema Property |
| JSON Schema | схема ниже |
| JSON Schema Version | Draft 2020-12 |

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "array",
  "minItems": 1,
  "items": {
    "type": "object",
    "required": ["driver_id", "car_id", "track_id", "status", "grid_position",
                 "race_date", "laps_completed"],
    "properties": {
      "driver_id":       {"type": "integer", "minimum": 1},
      "car_id":          {"type": "integer", "minimum": 1},
      "track_id":        {"type": "integer", "minimum": 1},
      "status":          {"enum": ["finished", "dnf", "dsq", "dns"]},
      "grid_position":   {"type": "integer", "minimum": 1, "maximum": 70},
      "finish_position": {"type": ["integer", "null"], "minimum": 1, "maximum": 70},
      "best_lap":        {"type": ["string", "null"], "pattern": "^\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,6})?$"},
      "total_time":      {"type": ["string", "null"], "pattern": "^\\d{2}:\\d{2}:\\d{2}(\\.\\d{1,6})?$"},
      "race_date":       {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
      "laps_completed":  {"type": "integer", "minimum": 0, "maximum": 1000}
    },
    "allOf": [
      {
        "if":   {"properties": {"status": {"const": "finished"}}},
        "then": {"properties": {"finish_position": {"type": "integer"},
                                "total_time":      {"type": "string"},
                                "best_lap":        {"type": "string"},
                                "laps_completed":  {"minimum": 1}}},
        "else": {"properties": {"finish_position": {"type": "null"},
                                "total_time":      {"type": "null"}}}
      },
      {
        "if":   {"properties": {"status": {"const": "dns"}}},
        "then": {"properties": {"laps_completed": {"const": 0}}}
      },
      {
        "if":   {"properties": {"status": {"const": "dsq"}}},
        "then": {"properties": {"best_lap": {"type": "null"}}}
      },
      {
        "if":   {"properties": {"laps_completed": {"const": 0}}},
        "then": {"properties": {"best_lap": {"type": "null"}}}
      }
    ]
  }
}
```

| Relationship | Куда |
|---|---|
| `valid` | `SplitJson` и журнал `received` |
| `invalid` | `Log errors`, `PutFile` в error, журнал `invalid` с `"message": "${json.validation.errors:escapeJson()}"` |
| `failure` | `Log errors` |

`ValidateJson` пишет описание ошибок в атрибут `json.validation.errors`.

Как схема повторяет твои `CHECK`:

| Правило в схеме | Ограничение в базе |
|---|---|
| `status` из списка | `chk_status` |
| `if finished then` место, время, лучший круг, ≥ 1 круга | `chk_finish_position`, `chk_total_time`, `chk_best_lap`, `chk_laps_completed_finish` |
| `else` место и время пустые | вторая половина `chk_finish_position` и `chk_total_time` (они записаны как равенство двух условий) |
| `dns` ⇒ 0 кругов | `chk_laps_completed_dns` |
| `dsq` ⇒ нет лучшего круга | `chk_best_lap_dsq` |
| 0 кругов ⇒ нет лучшего круга | `chk_best_lap_zero_laps` |
| позиции 1–70, круги 0–1000 | `chk_grid_position`, `chk_finish_position_range`, `chk_laps_completed_range` |

`allOf` — «должны выполняться все условия из списка»; внутри каждое правило оформлено парой `if`/`then` (и `else`, где нужно).

> Чего JSON Schema **не** умеет: правила между строками (уникальность стартовых позиций в гонке, один пилот — одна строка) и арифметику (`total_time >= best_lap * laps_completed`). Первое поймают `UNIQUE` и первичный ключ при вставке, второе — `chk_best_lap_cmp_total_time`. Если хочется отсекать и это до базы, нужен `QueryRecord` с SQL над записями файла (практика 3).

> Испорченный генератором файл (`--bad`) содержит финишировавшего без места. `ValidateJson` отклонит его целиком, и **ни одна** строка этой гонки не попадёт в базу. Сравни с уроком 6: без проверки 19 строк вставились бы, а одна упала.

Что проверяет каждый уровень:

| Проверка | Где | Ловит |
|---|---|---|
| маска имени | `RouteOnAttribute` | чужие файлы, опечатки в имени, неизвестный формат |
| разбор формата | `ConvertRecord` → `failure` | битый JSON/CSV |
| структура и значения | `ValidateJson` | нет поля, не тот тип, неверный статус, несогласованные статус/место/время/круги |
| ключи, уникальность, межстрочные правила | `PutDatabaseRecord` → `failure` | пилот уже ехал в этот день, повтор позиции, несуществующая машина, `total_time` меньше `best_lap × круги` |

Подробнее: [ValidateJson](https://nifi.apache.org/components/org.apache.nifi.processors.standard.ValidateJson/), [JSON Schema: Getting started](https://json-schema.org/learn/getting-started-step-by-step).

### Практика

1. Запусти генератор с `--bad 0.3 --interval 20` и через несколько минут покажи в `nifi_load_log` файлы со статусом `invalid` и текстом ошибки валидации.
2. Положи в `input` файл `hello.txt` и найди его в журнале и в папке `error`.
3. (*) Добавь `QueryRecord` после `ValidateJson`, который отсекает гонки с повторяющимися `grid_position` или `car_id` (подсказка: `SELECT * FROM FLOWFILE WHERE grid_position IN (SELECT grid_position FROM FLOWFILE GROUP BY grid_position HAVING count(*) > 1)` в отдельное свойство-relationship).

## Урок 11. Сохранение потока

Поток нужно сдать и не потерять при пересоздании контейнера.

1. Собери все процессоры в **Process Group**: выдели всё (Ctrl/Cmd+A) → правый клик → **Group** → имя `race_entry loader`.
2. Правый клик по группе → **Download Flow Definition** → JSON-файл. Положи его в `lab08/flow/`.
3. Загрузить обратно: перетащи значок **Process Group** на холст → кнопка загрузки файла справа от поля имени → выбери JSON.

> В NiFi 1.x для этого были шаблоны (templates). В NiFi 2 их убрали, вместо них Flow Definition.

> Пароли из controller services (`Password` в `DBCPConnectionPool`) в Flow Definition **не попадают**: после загрузки их нужно ввести заново. Это сделано специально, чтобы секреты не утекали вместе с файлом.

> Без тома для `/opt/nifi/nifi-current/conf` (и других каталогов состояния) поток живёт внутри контейнера: `docker compose down` и `up` его сохранят, а `docker compose down -v` или удаление контейнера — нет. Flow Definition в репозитории — самая надёжная копия.

### Практика

1. Выгрузи Flow Definition, удали группу с холста, загрузи обратно, введи пароль, включи сервисы и проверь, что поток работает.

---

# Итог: схема потока

```
                 ┌──────────────── unmatched ──▶ [Log errors] [PutFile error] [журнал: invalid]
[GetFile] ─▶ [Check name] ─valid─▶ [UpdateAttribute: file.id, target.table, file.ts, file.format]
                                         │
                                         ▼
                              [RouteOnAttribute: формат]
                         json ─┤                    ├─ csv          unmatched ─▶ [Log errors]
                               ▼                    ▼
                 [ConvertRecord JsonTreeReader] [ConvertRecord CSVReader]  ─failure─▶ [Log errors]
                               └────────┬───────────┘
                                        ▼
                                 [ValidateJson] ─invalid─▶ [Log errors] [PutFile error] [журнал: invalid]
                                        │ valid
                         ┌──────────────┴───────────────┐
                         ▼                              ▼
                    [SplitJson $.*]            [ReplaceText → журнал: received]
                         │ split
                         ▼
          [PutDatabaseRecord → ${target.table}] ─failure/retry─▶ [Log errors] [журнал: failed_record]
                         │ success
                         ▼
                    (terminate или LogAttribute)
```

Чек-лист сдачи:

- генератор работает с интервалом 5 минут, имена файлов соответствуют маске (id, таблица, дата-время);
- в потоке есть `GetFile`, `ConvertRecord` (разные читатели для JSON и CSV), `SplitJson`, `PutDatabaseRecord`, `LogAttribute`;
- в `race_entry` появляются целые гонки, ни одно ограничение не нарушено;
- `nifi_load_log` показывает принятые, отклонённые файлы и ошибочные записи;
- плохой файл (по имени и по содержимому) не доходит до таблицы и оказывается в `error`;
- Flow Definition выгружен в файл.

# Финальное задание

Сделай второй поток для другой таблицы, не подглядывая в уроки:

- Генератор `contract_generator.py` раз в 5 минут создаёт CSV с новыми контрактами для таблицы `contract`, маска та же. Контракт получают пилоты без открытого контракта (`end_date IS NULL`), команда — активная, `start_date` — сегодня (не позже сегодняшнего дня: `chk_contract_start_date`), `end_date` пустой.
- Поток в отдельной Process Group: свои схемы Avro и JSON Schema, своя проверка имени, `PutDatabaseRecord` в `contract`.
- Повторный контракт пилота с той же датой начала (первичный ключ `(driver_id, start_date)`) не должен ронять файл целиком: остальные записи вставляются, повтор попадает в журнал `failed_record` с текстом ошибки.
- (*) Перед вставкой нового контракта закрой предыдущий открытый контракт пилота: `PutDatabaseRecord` с `Statement Type = UPDATE` или `Pre-Processing SQL`. Подумай, как сделать, чтобы закрытие и вставка были в одной транзакции.
- Общий журнал `nifi_load_log` для обоих потоков; запрос, показывающий по каждой таблице число файлов, записей и ошибок за последний час.
- Flow Definition обоих потоков выгружен.

# Шпаргалка

```bash
docker compose up -d && docker logs -f nifi                    # https://localhost:8443/nifi
docker exec nifi tail -n 50 /opt/nifi/nifi-current/logs/nifi-app.log
python generator/generator.py --interval 300                   # для сдачи
python generator/generator.py --interval 20 --bad 0.3          # для отладки
export PGHOST=localhost PGPORT=5433 PGDATABASE=study PGUSER=postgres PGPASSWORD=postgres
```

```
Маска:   000042__race_entry__20261020_143000.json
Regex:   ^\d{6}__[a-z_]+__\d{8}_\d{6}\.(json|csv)$

EL:
${filename:substringBefore('__')}                               id файла
${filename:substringAfter('__'):substringBeforeLast('__')}      таблица
${filename:substringAfterLast('.'):toLower()}                   формат
${filename:matches('...')}                                      проверка маски
${putdatabaserecord.error:escapeJson()}                         ошибка вставки для JSON

JDBC:    jdbc:postgresql://host.docker.internal:5433/study?stringtype=unspecified   ← обязательно для date и interval
Driver:  org.postgresql.Driver, /opt/nifi/drivers/postgresql-42.7.14.jar

PutDatabaseRecord: INSERT, Table Name ${target.table}; все столбцы есть в записи → Fail on Unmatched Columns
SplitJson: $.*   → атрибуты fragment.identifier / index / count, segment.original.filename
ValidateJson → json.validation.errors   (allOf + if/then/else повторяют CHECK)
ReplaceText: Always Replace + Entire text → JSON журнала → PutDatabaseRecord в nifi_load_log
```

# Источники и что почитать дальше

**Официальная документация**
- [NiFi Getting Started](https://nifi.apache.org/docs/nifi-docs/html/getting-started.html) — термины, первый поток, работа с интерфейсом; ссылка из задания.
- [NiFi User Guide](https://nifi.apache.org/docs/nifi-docs/html/user-guide.html) — очереди, provenance, controller services, process groups.
- [Expression Language Guide](https://nifi.apache.org/docs/nifi-docs/html/expression-language-guide.html) — все функции `${...}`.
- [Список компонентов NiFi](https://nifi.apache.org/components/) — описания всех процессоров и сервисов с их свойствами.
- [PutDatabaseRecord](https://nifi.apache.org/components/org.apache.nifi.processors.standard.PutDatabaseRecord/) — все свойства, включая поведение с несовпадающими полями.
- [ValidateJson](https://nifi.apache.org/components/org.apache.nifi.processors.standard.ValidateJson/) — проверка по JSON Schema.
- [apache/nifi на Docker Hub](https://hub.docker.com/r/apache/nifi) — переменные окружения образа.
- [pgJDBC: использование драйвера](https://jdbc.postgresql.org/documentation/use/) — параметры URL, включая `stringtype`.

**Статьи и курсы**
- [JSON Schema: Getting started step-by-step](https://json-schema.org/learn/getting-started-step-by-step) — как писать схемы для `ValidateJson`.
- [Docker: Get started](https://docs.docker.com/get-started/) — если нужно подтянуть Docker.
