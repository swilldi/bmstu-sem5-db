# LINQ и PostgreSQL на C# (лабораторная 7)

Материал к лабораторной 7 «Использование технологии LINQ». Три части задания: LINQ to Objects, LINQ to JSON, LINQ к базе данных. Схема автогонок из лабы 1 (`driver`, `car`, `team`, `track`, `race_entry`, `contract`), функции и процедуры из лабы 3, база `study` на порту 5433.

В конце ты сможешь:
- писать LINQ-запросы в синтаксисе запросов и методов, понимать все ключевые слова;
- загрузить JSON из PostgreSQL и читать, менять и дополнять его через LINQ;
- описать таблицы базы классами, читать и менять данные через Entity Framework Core, включая составные ключи, `date` и `interval`;
- вызывать из C# свои функции и процедуры, получать их `RAISE NOTICE`.

Как проходить: по порядку, код набирать руками. Строим одно консольное приложение `Lab07`, каждая часть — отдельный файл, `Program.cs` вызывает их по очереди.

**Что нужно знать заранее**

- **C#** (большой раздел, по ходу не объясняется): классы и `record`, свойства, `List<T>`, nullable-типы (`short?`, `TimeSpan?`), лямбды, `async`/`await`, `partial`-классы. Если с этим слабо, сначала пройди [тур по языку C#](https://learn.microsoft.com/en-us/dotnet/csharp/tour-of-csharp/).
- **JSON в PostgreSQL** (лаба 5): `jsonb_agg`, `jsonb_build_object`.
- **Свои функции и процедуры из лабы 3** должны быть созданы в базе (урок 11).

**Про «LINQ to SQL».** Исторический LINQ to SQL — технология .NET Framework, работает только с MS SQL Server и в современном .NET отсутствует. Для PostgreSQL то же самое делают через **Entity Framework Core** с провайдером Npgsql. В отчёте так и стоит написать: «LINQ to SQL реализован через EF Core (LINQ to Entities), так как LINQ to SQL не поддерживает PostgreSQL».

**Содержание**

- Часть I. LINQ to Objects
  - [Урок 0. Окружение и проект](#урок-0-окружение-и-проект)
  - [Урок 1. Класс-таблица и загрузка коллекции](#урок-1-класс-таблица-и-загрузка-коллекции)
  - [Урок 2. from, where, select, orderby](#урок-2-from-where-select-orderby)
  - [Урок 3. join, let, into](#урок-3-join-let-into)
  - [Урок 4. group by](#урок-4-group-by)
  - [Урок 5. Пять запросов на все ключевые слова](#урок-5-пять-запросов-на-все-ключевые-слова)
- Часть II. LINQ to JSON
  - [Урок 6. JSON из базы в JsonNode](#урок-6-json-из-базы-в-jsonnode)
  - [Урок 7. Чтение, обновление, добавление](#урок-7-чтение-обновление-добавление)
- Часть III. LINQ к базе через EF Core
  - [Урок 8. Классы сущностей и DbContext](#урок-8-классы-сущностей-и-dbcontext)
  - [Урок 9. Запросы на выборку](#урок-9-запросы-на-выборку)
  - [Урок 10. Добавление, изменение, удаление](#урок-10-добавление-изменение-удаление)
  - [Урок 11. Доступ к данным через хранимую процедуру](#урок-11-доступ-к-данным-через-хранимую-процедуру)
- [Итог: структура проекта](#итог-структура-проекта)
- [Финальное задание](#финальное-задание)
- [Шпаргалка](#шпаргалка)
- [Источники](#источники-и-что-почитать-дальше)

---

# Часть I. LINQ to Objects

## Урок 0. Окружение и проект

Ставим .NET SDK, создаём проект, добавляем пакеты.

Нужен .NET SDK 8 или новее:

```bash
dotnet --version
```

Если команды нет, поставь SDK с [dotnet.microsoft.com](https://dotnet.microsoft.com/download).

```bash
dotnet new console -n Lab07
cd Lab07
dotnet add package Npgsql
dotnet add package Npgsql.EntityFrameworkCore.PostgreSQL
dotnet add package Microsoft.EntityFrameworkCore.Design
dotnet tool install --global dotnet-ef
```

| Пакет | Зачем |
|---|---|
| `Npgsql` | драйвер PostgreSQL (части I и II) |
| `Npgsql.EntityFrameworkCore.PostgreSQL` | провайдер EF Core для PostgreSQL (часть III) |
| `Microsoft.EntityFrameworkCore.Design` | нужен `dotnet ef` для генерации классов |
| `dotnet-ef` | консольная утилита EF Core |

> Мажорная версия EF Core совпадает с версией .NET: EF Core 10 требует .NET 10, EF Core 8 — .NET 8. `dotnet add package` без версии берёт самую новую, и на старом SDK сборка упадёт с ошибкой про target framework. Тогда укажи версию явно: `--version 8.*` для всех трёх EF-пакетов, или поставь новый SDK.

Строка подключения — в переменной окружения. Порт **5433** — проброс твоего контейнера `study-pg`:

```bash
export LAB_DB="Host=localhost;Port=5433;Database=study;Username=postgres;Password=postgres"
```

`Program.cs` пока такой:

```csharp
var cs = Environment.GetEnvironmentVariable("LAB_DB")
         ?? throw new InvalidOperationException("Задай переменную LAB_DB");
Console.WriteLine("Строка подключения найдена");
```

```bash
dotnet run
```

### Практика

1. Создай проект, добавь пакеты, убедись, что `dotnet run` печатает сообщение, а без `LAB_DB` падает с понятной ошибкой.

## Урок 1. Класс-таблица и загрузка коллекции

Пункт 1 лабы: коллекция объектов, структура которых полностью соответствует таблице. Основная коллекция — `race_entry`; для `join` понадобятся `driver` и `track`.

`Objects/Rows.cs`:

```csharp
namespace Lab07.Objects;

// один в один со столбцами таблиц
public record RaceEntryRow(
    int DriverId,
    int CarId,
    int TrackId,
    string Status,
    short GridPosition,
    short? FinishPosition,     // NULL у сошедших
    TimeSpan? BestLap,         // interval, NULL у dns/dsq
    TimeSpan? TotalTime,       // interval, есть только у finished
    DateOnly RaceDate,
    short LapsCompleted);

public record DriverRow(
    int DriverId,
    string FullName,
    DateOnly BirthDate,
    string BirthCity,
    string Country,
    string LicenseClass,
    short DebutYear);

public record TrackRow(
    int TrackId,
    string Name,
    string Country,
    decimal LengthKm,
    string TrackType,
    short OpenedYear);
```

`record` — класс, у которого из короткой записи генерируются свойства, конструктор, `ToString()` и сравнение по значению.

| PostgreSQL | C# |
|---|---|
| `serial`, `int` | `int` |
| `smallint` | `short` |
| `numeric(6,2)` | `decimal` |
| `text` | `string` |
| `date` | `DateOnly` |
| `interval` | `TimeSpan` |
| `boolean` | `bool` |
| столбец без `NOT NULL` | `short?`, `TimeSpan?`, `int?` |

`Objects/Loader.cs`:

```csharp
using Npgsql;

namespace Lab07.Objects;

public static class Loader
{
    public static async Task<List<RaceEntryRow>> LoadEntries(NpgsqlDataSource ds)
    {
        var list = new List<RaceEntryRow>(60_000);
        await using var cmd = ds.CreateCommand("""
            SELECT driver_id, car_id, track_id, status, grid_position, finish_position,
                   best_lap, total_time, race_date, laps_completed
            FROM race_entry
            """);
        await using var r = await cmd.ExecuteReaderAsync();
        while (await r.ReadAsync())
        {
            list.Add(new RaceEntryRow(
                r.GetInt32(0), r.GetInt32(1), r.GetInt32(2), r.GetString(3),
                r.GetInt16(4),
                r.IsDBNull(5) ? null : r.GetInt16(5),
                r.IsDBNull(6) ? null : r.GetTimeSpan(6),
                r.IsDBNull(7) ? null : r.GetTimeSpan(7),
                r.GetFieldValue<DateOnly>(8),
                r.GetInt16(9)));
        }
        return list;
    }

    public static async Task<List<DriverRow>> LoadDrivers(NpgsqlDataSource ds)
    {
        var list = new List<DriverRow>();
        await using var cmd = ds.CreateCommand("""
            SELECT driver_id, full_name, birth_date, birth_city, country, license_class, debut_year
            FROM driver
            """);
        await using var r = await cmd.ExecuteReaderAsync();
        while (await r.ReadAsync())
            list.Add(new DriverRow(r.GetInt32(0), r.GetString(1), r.GetFieldValue<DateOnly>(2),
                r.GetString(3), r.GetString(4), r.GetString(5), r.GetInt16(6)));
        return list;
    }

    public static async Task<List<TrackRow>> LoadTracks(NpgsqlDataSource ds)
    {
        var list = new List<TrackRow>();
        await using var cmd = ds.CreateCommand(
            "SELECT track_id, name, country, length_km, track_type, opened_year FROM track");
        await using var r = await cmd.ExecuteReaderAsync();
        while (await r.ReadAsync())
            list.Add(new TrackRow(r.GetInt32(0), r.GetString(1), r.GetString(2),
                r.GetDecimal(3), r.GetString(4), r.GetInt16(5)));
        return list;
    }
}
```

`Program.cs`:

```csharp
using Lab07.Objects;
using Npgsql;

var cs = Environment.GetEnvironmentVariable("LAB_DB")
         ?? throw new InvalidOperationException("Задай переменную LAB_DB");
await using var ds = NpgsqlDataSource.Create(cs);

var entries = await Loader.LoadEntries(ds);
var drivers = await Loader.LoadDrivers(ds);
var tracks = await Loader.LoadTracks(ds);
Console.WriteLine($"Загружено: {entries.Count} заездов, {drivers.Count} пилотов, {tracks.Count} трасс");
```

`NpgsqlDataSource` — фабрика соединений с пулом; создаётся один раз.

> `GetInt16` для `smallint`, а не `GetInt32`: Npgsql строг к типам и бросит `InvalidCastException`, если запросить `int` у `smallint`. Это частая ошибка при первой загрузке.

> `GetTimeSpan` работает для твоих интервалов, потому что в них только часы, минуты и секунды. Интервал с месяцами (`'1 month'`) в `TimeSpan` не переводится однозначно (сколько дней в месяце?), и Npgsql бросит исключение.

> Номера в `GetInt32(0)` — порядковые номера столбцов в `SELECT`, поэтому `SELECT *` здесь не используем.

### Практика

1. Добавь `CarRow` и `TeamRow` (у команды `int? TeamParentId`) с загрузкой и выведи число активных команд.
2. (*) Добавь `ContractRow` с `DateOnly? EndDate` и выведи число открытых контрактов (должно быть 188).

## Урок 2. from, where, select, orderby

LINQ to Objects — запросы к коллекциям в памяти. Начнём с базового синтаксиса.

`LinqToObjects.cs`:

```csharp
using Lab07.Objects;

namespace Lab07;

public static class LinqToObjects
{
    public static void Basics(List<RaceEntryRow> entries)
    {
        // синтаксис запросов
        var wins =
            from e in entries
            where e.FinishPosition == 1
            orderby e.RaceDate descending
            select new { e.RaceDate, e.DriverId, e.TotalTime };

        foreach (var w in wins.Take(5))
            Console.WriteLine($"{w.RaceDate}  пилот {w.DriverId}  {w.TotalTime:hh\\:mm\\:ss\\.fff}");

        // то же в синтаксисе методов
        var wins2 = entries
            .Where(e => e.FinishPosition == 1)
            .OrderByDescending(e => e.RaceDate)
            .Select(e => new { e.RaceDate, e.DriverId, e.TotalTime });
    }
}
```

Компилятор превращает синтаксис запросов в вызовы методов: `where` → `.Where(...)`, `orderby ... descending` → `.OrderByDescending(...)`, `select` → `.Select(...)`.

`TimeSpan` форматируется своими спецификаторами: `hh\:mm\:ss\.fff`, двоеточие и точка экранируются обратным слэшем.

Сортировка по нескольким ключам:

```csharp
var sorted =
    from e in entries
    orderby e.RaceDate ascending, e.FinishPosition ascending
    select e;
```

`ascending` — направление по умолчанию, но его можно написать явно (в уроке 5 нужны все ключевые слова).

**Отложенное выполнение.** Запрос выполняется при переборе, а не при объявлении:

```csharp
var q = from e in entries where e.Status == "dsq" select e;
entries.Add(entries[0] with { Status = "dsq", FinishPosition = null });
Console.WriteLine(q.Count());   // новая строка учтена
```

> Каждый перебор выполняет запрос заново. По 54 тысячам строк это уже ощутимо: если результат нужен несколько раз, `var list = q.ToList();`.

> `e.FinishPosition == 1` для `short?` безопасно и для `null` (просто `false`). А `e.FinishPosition.Value` на сошедшем упадёт.

> `orderby e.FinishPosition` ставит `null` **в начало** (в C# `null` меньше любого числа). В SQL у PostgreSQL наоборот: `NULLS LAST` по умолчанию при возрастании. Не удивляйся разнице.

Подробнее: [Query keywords](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/keywords/query-keywords).

### Практика

1. Выведи 10 самых быстрых кругов (`BestLap`) в истории с датой и трассой (`TrackId` пока числом).
2. Перепиши запрос в синтаксисе методов и проверь совпадение (`SequenceEqual`).

## Урок 3. join, let, into

Соединяем коллекции, вводим промежуточные переменные, группируем при соединении.

`join ... on ... equals`:

```csharp
var withNames =
    from e in entries
    join d in drivers on e.DriverId equals d.DriverId
    where e.FinishPosition == 1
    select new { d.FullName, e.RaceDate };
```

> В `join` обязательно `equals`, а не `==`; слева переменная первой коллекции, справа второй.

`let` — переменная внутри запроса. Самые молодые победители:

```csharp
var youngWinners =
    from e in entries
    join d in drivers on e.DriverId equals d.DriverId
    where e.FinishPosition == 1
    let age = e.RaceDate.Year - d.BirthDate.Year
              - (e.RaceDate.DayOfYear < d.BirthDate.DayOfYear ? 1 : 0)
    orderby age
    select new { d.FullName, Age = age, e.RaceDate };
```

Составной ключ в `join` — анонимный тип. Соединим заезд с трассой и «гонкой» (пара трасса + дата):

```csharp
var races = entries.Select(e => new { e.TrackId, e.RaceDate }).Distinct().ToList();

var raceSizes =
    from r in races
    join e in entries on new { r.TrackId, r.RaceDate } equals new { e.TrackId, e.RaceDate } into re
    select new { r.TrackId, r.RaceDate, Starters = re.Count() };
```

> В составном ключе имена и типы свойств анонимных объектов слева и справа должны совпадать: `new { r.TrackId, r.RaceDate }` и `new { e.TrackId, e.RaceDate }`. Если слева назвать `Track = r.TrackId`, а справа `TrackId`, будет ошибка компиляции.

`join ... into` — групповое соединение: каждому элементу слева достаётся **коллекция** совпадений справа (аналог `LEFT JOIN` + группировки):

```csharp
var trackStats =
    from t in tracks
    join e in entries on t.TrackId equals e.TrackId into te
    select new { t.Name, Entries = te.Count(), Races = te.Select(x => x.RaceDate).Distinct().Count() };
```

Трассы без гонок здесь тоже есть, с нулями.

### Практика

1. Для каждого пилота выведи число стартов, побед и дату последней гонки (групповой `join`), только пилотов с хотя бы одной победой.
2. Через `let` посчитай для каждого финиша «отыгранные позиции» (`GridPosition - FinishPosition`) и выведи 10 лучших прорывов с именем пилота.

## Урок 4. group by

`group ... by` — группировка, как `GROUP BY` в SQL.

```csharp
var byStatus =
    from e in entries
    group e by e.Status;

foreach (var g in byStatus)
    Console.WriteLine($"{g.Key}: {g.Count()}");
```

`group ... by ... into` — продолжить запрос после группировки:

```csharp
var prolific =
    from e in entries
    where e.FinishPosition == 1
    group e by e.DriverId into g
    where g.Count() >= 10
    orderby g.Count() descending
    select new { DriverId = g.Key, Wins = g.Count(), First = g.Min(x => x.RaceDate) };
```

Составной ключ — анонимный тип. Число гонок по десятилетиям и типам трасс:

```csharp
var byDecade =
    from e in entries
    join t in tracks on e.TrackId equals t.TrackId
    group e by new { Decade = e.RaceDate.Year / 10 * 10, t.TrackType } into g
    orderby g.Key.Decade, g.Key.TrackType
    select new { g.Key.Decade, g.Key.TrackType, Entries = g.Count() };
```

> После `into` прежняя переменная `e` недоступна, остаётся только `g`. Частая ошибка «The name 'e' does not exist in the current context».

> `g.Average(x => x.BestLap)` не скомпилируется: у `TimeSpan` нет стандартного `Average`. Усредняй в секундах: `TimeSpan.FromSeconds(g.Where(x => x.BestLap != null).Average(x => x.BestLap!.Value.TotalSeconds))`.

### Практика

1. Сгруппируй пилотов по стране и выведи 10 стран с наибольшим числом пилотов, у которых есть хотя бы одна победа.
2. (*) Средний лучший круг по десятилетиям на одной трассе (выбери трассу, где гонки шли долго). Видно ли, что машины стали быстрее?

## Урок 5. Пять запросов на все ключевые слова

Пункт 1 требует не менее пяти запросов, которые вместе используют **все** ключевые слова выражения запроса.

| Ключевое слово | Где использовано |
|---|---|
| `from`, `in`, `select` | все запросы |
| `where` | 1, 2, 5 |
| `orderby`, `ascending`, `descending` | 1, 3, 5 |
| `join`, `on`, `equals` | 2, 4 |
| `into` | 3 (после `group`), 4 (после `join`) |
| `group`, `by` | 3 |
| `let` | 2 |

```csharp
public static void FiveQueries(List<RaceEntryRow> entries, List<DriverRow> drivers, List<TrackRow> tracks)
{
    // 1. from, in, where, orderby, descending, select
    var q1 =
        from e in entries
        where e.BestLap != null && e.Status == "finished"
        orderby e.RaceDate descending
        select new { e.RaceDate, e.DriverId, e.TrackId, e.BestLap };
    Print("1. Последние финиши с лучшим кругом", q1.Take(10));

    // 2. join, on, equals, let, where
    var q2 =
        from e in entries
        join d in drivers on e.DriverId equals d.DriverId
        where e.FinishPosition == 1
        let age = e.RaceDate.Year - d.BirthDate.Year
        where age < 23
        select new { d.FullName, Age = age, e.RaceDate };
    Print("2. Победители моложе 23 лет", q2.Take(15));

    // 3. group, by, into, orderby, ascending
    var q3 =
        from e in entries
        group e by e.Status into g
        orderby g.Key ascending
        select new { Status = g.Key, Count = g.Count(), AvgLaps = Math.Round(g.Average(x => (double)x.LapsCompleted), 1) };
    Print("3. Заезды по статусам", q3);

    // 4. join ... into (групповое соединение)
    var q4 =
        from t in tracks
        join e in entries on t.TrackId equals e.TrackId into te
        select new { t.Name, t.TrackType, Races = te.Select(x => x.RaceDate).Distinct().Count() };
    Print("4. Трассы и число гонок", q4.OrderByDescending(x => x.Races).Take(10));

    // 5. несколько from, where, orderby с двумя ключами
    var lastYear = entries.Max(e => e.RaceDate).Year;
    var q5 =
        from d in drivers
        from e in entries
        where e.DriverId == d.DriverId && e.Status == "dnf" && e.RaceDate.Year == lastYear
        orderby d.FullName ascending, e.RaceDate descending
        select new { d.FullName, e.RaceDate, e.LapsCompleted };
    Print($"5. Сходы в сезоне {lastYear}", q5.Take(15));
}

static void Print<T>(string title, IEnumerable<T> items)
{
    Console.WriteLine($"\n== {title} ==");
    foreach (var item in items) Console.WriteLine(item);
}
```

> Запрос 5 (два `from`) по смыслу то же, что `join`, но перебирает **все пары**: 6 тысяч пилотов × 54 тысячи заездов = 330 миллионов проверок. На твоих данных это уже секунды, а не миллисекунды. Запусти и сравни с `join`: так на защите наглядно видно, почему `join` строит хеш-таблицу. Два `from` нужны, когда условие не равенство.

В `Program.cs`:

```csharp
LinqToObjects.FiveQueries(entries, drivers, tracks);
```

Подробнее: [LINQ overview](https://learn.microsoft.com/en-us/dotnet/csharp/linq/), [Standard query operators](https://learn.microsoft.com/en-us/dotnet/csharp/linq/standard-query-operators/).

### Практика

1. Напиши свои пять запросов на коллекциях `CarRow` и `TeamRow` так, чтобы вместе они покрыли все ключевые слова. Отметь в комментарии у каждого, какие слова он покрывает.
2. Замерь время запроса 5 через `System.Diagnostics.Stopwatch` и время того же запроса через `join`.

# Часть II. LINQ to JSON

## Урок 6. JSON из базы в JsonNode

Пункт 2 лабы: создать JSON-документ, извлекая его из таблиц через `SELECT`, и работать с ним через LINQ. JSON собирает PostgreSQL (как в лабе 5), C# получает строку.

`System.Text.Json.Nodes` даёт `JsonNode`, `JsonObject`, `JsonArray`. `JsonArray` реализует `IEnumerable<JsonNode?>`, к нему применим LINQ.

Документ: 10 трасс с наибольшим числом гонок, у каждой массив гонок с победителем и лучшим кругом.

`LinqToJson.cs`:

```csharp
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using Npgsql;

namespace Lab07;

public static class LinqToJson
{
    static readonly JsonSerializerOptions Pretty = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping   // не экранировать не-ASCII
    };

    public static async Task<JsonArray> LoadTracks(NpgsqlDataSource ds)
    {
        await using var cmd = ds.CreateCommand("""
            WITH top_tracks AS (
                SELECT track_id FROM race_entry
                GROUP BY track_id
                ORDER BY count(DISTINCT race_date) DESC
                LIMIT 10)
            SELECT jsonb_agg(jsonb_build_object(
                     'track_id', t.track_id,
                     'name',     t.name,
                     'country',  t.country,
                     'km',       t.length_km,
                     'races', (SELECT jsonb_agg(jsonb_build_object(
                                  'date',     re.race_date,
                                  'winner',   d.full_name,
                                  'time',     re.total_time,
                                  'best_lap_s', extract(epoch FROM re.best_lap))
                                ORDER BY re.race_date)
                               FROM race_entry re JOIN driver d ON d.driver_id = re.driver_id
                               WHERE re.track_id = t.track_id AND re.finish_position = 1)))::text
            FROM track t
            WHERE t.track_id IN (SELECT track_id FROM top_tracks)
            """);
        var json = (string)(await cmd.ExecuteScalarAsync())!;
        return JsonNode.Parse(json)!.AsArray();
    }

    public static void Save(JsonNode doc, string path) =>
        File.WriteAllText(path, doc.ToJsonString(Pretty));
}
```

В `Program.cs`:

```csharp
var tracksJson = await LinqToJson.LoadTracks(ds);
LinqToJson.Save(tracksJson, "tracks.json");
Console.WriteLine($"В документе {tracksJson.Count} трасс, сохранён в tracks.json");
```

> Лучший круг кладём в документ **числом секунд** (`extract(epoch FROM ...)`), а общее время оставляем строкой `"02:13:23.6"`. Так в C# удобно сравнивать круги как числа, а заодно ты увидишь оба способа хранить интервал в JSON.

> Без `JavaScriptEncoder.UnsafeRelaxedJsonEscaping` все символы вне ASCII (имена вроде «Räikkönen», «Pérez») в файле станут `ä`. Это валидный JSON, но читать глазами неудобно.

| Класс | Что это |
|---|---|
| `JsonNode` | любой узел JSON |
| `JsonObject` | объект, доступ `node["key"]` |
| `JsonArray` | массив, доступ `node[0]`, перебор `foreach` |
| `JsonValue` | скаляр; значение через `GetValue<T>()` |

Подробнее: [Use JsonNode (DOM)](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-dom).

### Практика

1. Сделай второй документ `teams.json`: команды с массивом дочерних команд (`team_parent_id`) и числом побед каждой (через машины).

## Урок 7. Чтение, обновление, добавление

Три запроса пункта 2: чтение, обновление, запись (добавление).

**Чтение.** Рекорд круга на каждой трассе и кто его поставил:

```csharp
public static void Read(JsonArray tracks)
{
    var records =
        from t in tracks
        let races = t!["races"]!.AsArray()
        let best = races
            .Where(r => r!["best_lap_s"] != null)
            .OrderBy(r => r!["best_lap_s"]!.GetValue<double>())
            .FirstOrDefault()
        where best != null
        orderby best["best_lap_s"]!.GetValue<double>()
        select new
        {
            Track = t["name"]!.GetValue<string>(),
            Winner = best["winner"]!.GetValue<string>(),
            Date = best["date"]!.GetValue<string>(),
            Lap = TimeSpan.FromSeconds(best["best_lap_s"]!.GetValue<double>())
        };

    foreach (var r in records) Console.WriteLine(r);
}
```

Запрос по вложенному массиву: все победы одного пилота на этих трассах:

```csharp
var schumacher =
    from t in tracks
    from r in t!["races"]!.AsArray()
    where r!["winner"]!.GetValue<string>().Contains("Schumacher")
    select new { Track = t["name"]!.GetValue<string>(), Date = r["date"]!.GetValue<string>() };
```

> `GetValue<double>()` для `best_lap_s`: `extract(epoch ...)` возвращает `numeric`, в JSON это число с дробью, и в C# его удобно читать как `double`. `GetValue<int>()` упал бы на дробной части.

> `TimeSpan.Parse(r["time"]!.GetValue<string>())` превратит строку `"02:13:23.6"` обратно в `TimeSpan`. Формат PostgreSQL для интервалов меньше суток совпадает с форматом `TimeSpan`, поэтому разбор работает.

**Обновление.** Перевести длину трасс в мили и пометить документ:

```csharp
public static void Update(JsonArray tracks)
{
    var items = tracks.Select(t => t!.AsObject()).ToList();     // материализуем до изменения
    foreach (var t in items)
    {
        var km = t["km"]!.GetValue<decimal>();
        t["miles"] = Math.Round(km / 1.609344m, 2);
        t["races_count"] = t["races"]!.AsArray().Count;
    }
    Console.WriteLine($"Обновлено трасс: {items.Count}");
}
```

> `ToList()` перед изменением — правило: не меняй коллекцию, которую сейчас перебирает LINQ-запрос. Менять свойства элементов можно, а добавлять/удалять элементы массива во время перебора нельзя (`Collection was modified`).

**Добавление.** Новая гонка на первой трассе и новая трасса:

```csharp
public static void Add(JsonArray tracks)
{
    var first = tracks[0]!.AsObject();
    first["races"]!.AsArray().Add(new JsonObject
    {
        ["date"] = DateOnly.FromDateTime(DateTime.Today).ToString("yyyy-MM-dd"),
        ["winner"] = "Новый Победитель",
        ["time"] = new TimeSpan(1, 31, 44).ToString(),
        ["best_lap_s"] = 81.237
    });

    tracks.Add(new JsonObject
    {
        ["track_id"] = null,                 // id появится, когда трасса попадёт в базу
        ["name"] = "Moscow Raceway",
        ["country"] = "Russia",
        ["km"] = 3.93m,
        ["races"] = new JsonArray()
    });
}
```

Всё вместе в `Program.cs`:

```csharp
var tracksJson = await LinqToJson.LoadTracks(ds);
LinqToJson.Save(tracksJson, "tracks.json");
LinqToJson.Read(tracksJson);
LinqToJson.Update(tracksJson);
LinqToJson.Add(tracksJson);
LinqToJson.Save(tracksJson, "tracks_updated.json");
```

Сравни два файла, чтобы показать результат на защите.

**Если нужен XML.** Задание позволяет XML. Тогда PostgreSQL собирает документ через `xmlelement`/`xmlagg` или `query_to_xml('SELECT * FROM track', true, false, '')`, в C# его читает `XDocument.Parse(...)`, запросы идут по `doc.Descendants("row")`, изменения через `SetElementValue`, добавление через `root.Add(new XElement(...))`. Подробнее в [LINQ to XML overview](https://learn.microsoft.com/en-us/dotnet/standard/linq/linq-xml-overview).

### Практика

1. Для `teams.json`: чтение — команды, у которых дочерние вместе выиграли больше, чем сама команда; обновление — пометить `"is_active": false` у всех команд без побед; добавление — новая дочерняя команда.
2. (*) После изменений запиши документ обратно в базу (`json_import` из лабы 5) параметром `NpgsqlDbType.Jsonb`.

<details><summary>Подсказка</summary>

`cmd.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlTypes.NpgsqlDbType.Jsonb, Value = doc.ToJsonString() });` и `INSERT INTO json_import (file_name, doc) VALUES ('teams.json', $1)`.

</details>

# Часть III. LINQ к базе через EF Core

## Урок 8. Классы сущностей и DbContext

Пункт 3 лабы: классы сущностей, моделирующие таблицы. EF Core генерирует их по существующей базе (scaffolding).

```bash
dotnet ef dbcontext scaffold "$LAB_DB" Npgsql.EntityFrameworkCore.PostgreSQL \
    --output-dir Models --context RacingContext --no-onconfiguring \
    --table driver --table car --table team --table track --table race_entry --table contract
```

`--table` ограничивает генерацию твоими шестью таблицами: иначе в модель попадут `json_import`, `race_entry_audit`, `pit_stop` и всё, что ты создавал в других лабах.

Получится по классу на таблицу: `Driver`, `Car`, `Team`, `Track`, `RaceEntry`, `Contract`. Например, `Models/RaceEntry.cs` примерно такой:

```csharp
public partial class RaceEntry
{
    public int DriverId { get; set; }
    public int CarId { get; set; }
    public int TrackId { get; set; }
    public string Status { get; set; } = null!;
    public short GridPosition { get; set; }
    public short? FinishPosition { get; set; }
    public TimeSpan? BestLap { get; set; }
    public TimeSpan? TotalTime { get; set; }
    public DateOnly RaceDate { get; set; }
    public short LapsCompleted { get; set; }

    public virtual Car Car { get; set; } = null!;
    public virtual Driver Driver { get; set; } = null!;
    public virtual Track Track { get; set; } = null!;
}
```

А в контексте:

```csharp
modelBuilder.Entity<RaceEntry>(entity =>
{
    entity.HasKey(e => new { e.DriverId, e.RaceDate }).HasName("pk_race_entry");
    entity.ToTable("race_entry");
    entity.HasIndex(e => new { e.TrackId, e.RaceDate, e.CarId }, "uq_race_entry_car").IsUnique();
    // ...
    entity.HasOne(d => d.Driver).WithMany(p => p.RaceEntries)
          .HasForeignKey(d => d.DriverId).HasConstraintName("fk_driver");
});
```

Что здесь важно для твоей схемы:

| Особенность | Как это видит EF |
|---|---|
| составной PK `(driver_id, race_date)` | `HasKey(e => new { e.DriverId, e.RaceDate })` |
| составной PK контракта `(driver_id, start_date)` | `HasKey(e => new { e.DriverId, e.StartDate })` |
| `interval` | `TimeSpan` |
| `date` | `DateOnly` |
| самоссылка `team.team_parent_id` | `Team.TeamParent` и коллекция `Team.InverseTeamParent` |
| `UNIQUE` | `HasIndex(...).IsUnique()` |
| `CHECK` | в модели обычно не появляются: проверяет база |

Ограничения в твоей базе добавлены через `ALTER TABLE` в отдельном файле. Для scaffold это неважно: он читает то, что есть в каталоге базы сейчас.

Создание контекста и перехват `RAISE NOTICE`. `Db.cs`:

```csharp
using Lab07.Models;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace Lab07;

public static class Db
{
    public static RacingContext Create(string cs, bool logSql = false)
    {
        var options = new DbContextOptionsBuilder<RacingContext>().UseNpgsql(cs);
        if (logSql)
            options.LogTo(Console.WriteLine, Microsoft.Extensions.Logging.LogLevel.Information);
        var db = new RacingContext(options.Options);

        // NOTICE из процедур (урок 11)
        var conn = (NpgsqlConnection)db.Database.GetDbConnection();
        conn.Notice += (_, e) => Console.WriteLine($"[NOTICE] {e.Notice.MessageText}");
        return db;
    }
}
```

`LogTo` печатает каждый SQL, отправленный в базу. Включи хотя бы раз и покажи на защите, во что превратился LINQ.

> Если изменишь таблицы, перегенерируй классы той же командой с `--force`. Правки в сгенерированных файлах потеряются, поэтому свой код пиши в отдельных `partial`-файлах.

> Если в лабе 5 ты добавил `car.specs jsonb`, scaffold сгенерирует `public string? Specs`: Npgsql отображает `jsonb` в строку. Работать с ним можно как с текстом JSON или настроить `JsonDocument`/свой класс, но для этой лабы строки хватит.

Подробнее: [Scaffolding](https://learn.microsoft.com/en-us/ef/core/managing-schemas/scaffolding/), [Npgsql EF Core provider](https://www.npgsql.org/efcore/).

### Практика

1. Сгенерируй модели и найди в контексте описание `uq_race_entry_finish_position` и `chk_*`. Каких ограничений в модели нет и почему это не страшно?
2. Найди навигационные свойства самоссылки у `Team` и выведи через них 5 команд с родителями: `db.Teams.Where(t => t.TeamParent != null).Select(t => new { t.Name, Parent = t.TeamParent!.Name }).Take(5)`.

## Урок 9. Запросы на выборку

Однотабличный и многотабличный запросы. LINQ пишется так же, как в части I, но превращается в SQL.

`LinqToDb.cs`:

```csharp
using Lab07.Models;
using Microsoft.EntityFrameworkCore;

namespace Lab07;

public static class LinqToDb
{
    // 1. Однотабличный
    public static async Task SingleTable(RacingContext db)
    {
        var query =
            from t in db.Tracks
            where t.TrackType == "street" && t.LengthKm > 3
            orderby t.LengthKm descending
            select new { t.Name, t.Country, t.LengthKm, t.OpenedYear };

        Console.WriteLine(query.ToQueryString());
        foreach (var t in await query.ToListAsync())
            Console.WriteLine(t);
    }

    // 2. Многотабличный: через join
    public static async Task MultiTableJoin(RacingContext db)
    {
        var query =
            from re in db.RaceEntries
            join d in db.Drivers on re.DriverId equals d.DriverId
            join c in db.Cars on re.CarId equals c.CarId
            join tm in db.Teams on c.TeamId equals tm.TeamId
            join t in db.Tracks on re.TrackId equals t.TrackId
            where re.FinishPosition == 1 && re.RaceDate.Year >= 2020
            orderby re.RaceDate descending
            select new { re.RaceDate, Track = t.Name, d.FullName, Team = tm.Name, re.TotalTime };

        foreach (var row in await query.Take(15).ToListAsync())
            Console.WriteLine(row);
    }

    // 2б. Многотабличный: через навигационные свойства
    public static async Task MultiTableNav(RacingContext db)
    {
        var teams = await db.Teams
            .Where(t => t.IsActive)
            .Select(t => new
            {
                t.Name,
                Parent = t.TeamParent != null ? t.TeamParent.Name : "—",
                Cars = t.Cars.Count,
                Wins = t.Cars.SelectMany(c => c.RaceEntries).Count(re => re.FinishPosition == 1),
                Drivers = t.Contracts.Count(k => k.EndDate == null)
            })
            .OrderByDescending(x => x.Wins)
            .Take(10)
            .ToListAsync();

        teams.ForEach(Console.WriteLine);
    }
}
```

В `Program.cs`:

```csharp
await using var db = Db.Create(cs, logSql: false);
await LinqToDb.SingleTable(db);
await LinqToDb.MultiTableJoin(db);
await LinqToDb.MultiTableNav(db);
```

`ToQueryString()` показывает SQL. Посмотри, как `re.RaceDate.Year >= 2020` превратилось в `date_part('year', r.race_date)::int >= 2020`: Npgsql умеет переводить свойства `DateOnly` в функции PostgreSQL.

| | `List<T>` (часть I) | `DbSet<T>` / `IQueryable<T>` (часть III) |
|---|---|---|
| Где выполняется | в памяти C# | в базе, как SQL |
| Лямбды | обычный код | дерево выражений, переводится в SQL |
| Любой C#-метод в `where` | можно | только то, что EF умеет перевести |

> `IsActive` может сгенерироваться как `bool` или `bool?` в зависимости от версии EF: в базе у него `DEFAULT true`. Если `bool?`, пиши `t.IsActive == true`.

> Свой C#-метод в запросе к `DbSet` EF перевести не сможет: `could not be translated`. Перепиши условие стандартными операциями или фильтруй после `ToListAsync()`.

> Сравни время: LINQ to Objects из части I сначала тянул все 54 тысячи заездов в память, а здесь база возвращает только 15 строк. Именно поэтому для больших таблиц запросы пишут к `DbSet`, а не к загруженному списку.

Подробнее: [EF Core](https://learn.microsoft.com/en-us/ef/core/).

### Практика

1. Однотабличный: пилоты с лицензией `super`, дебютировавшие после 2010 года, по году дебюта; выведи SQL через `ToQueryString()`.
2. Многотабличный: для выбранного пилота все его команды по контрактам, с датами и числом гонок за машины этой команды.
3. (*) Перепиши п.2 двумя способами (`join` и навигация) и сравни SQL.

## Урок 10. Добавление, изменение, удаление

Три запроса на изменение. EF отслеживает загруженные объекты и при `SaveChangesAsync()` отправляет `INSERT`/`UPDATE`/`DELETE`.

```csharp
public static async Task Crud(RacingContext db)
{
    // ДОБАВЛЕНИЕ
    var team = new Team
    {
        Name = $"Lab07 Racing {Random.Shared.Next(1000, 9999)}",   // UNIQUE (name)
        Country = "Russia",
        FoundedYear = 2026,
        IsActive = true
    };
    db.Teams.Add(team);
    await db.SaveChangesAsync();
    Console.WriteLine($"Добавлена команда id={team.TeamId}");

    // ИЗМЕНЕНИЕ
    var found = await db.Teams.SingleAsync(t => t.TeamId == team.TeamId);
    found.Country = "Kazakhstan";
    found.IsActive = false;
    await db.SaveChangesAsync();
    Console.WriteLine("Команда изменена");

    // УДАЛЕНИЕ
    db.Teams.Remove(found);
    await db.SaveChangesAsync();
    Console.WriteLine("Команда удалена");
}
```

`SingleAsync` загрузил объект и запомнил исходные значения (change tracking). При `SaveChangesAsync` EF отправил `UPDATE team SET country = ..., is_active = ... WHERE team_id = ...`.

**Составной ключ.** Контракт пилота с новой командой и поиск по ключу:

```csharp
var start = DateOnly.FromDateTime(DateTime.Today);
db.Contracts.Add(new Contract { DriverId = 20, TeamId = team.TeamId, StartDate = start });
await db.SaveChangesAsync();

var contract = await db.Contracts.FindAsync(20, start);   // порядок как в HasKey: (DriverId, StartDate)
contract!.EndDate = start;
await db.SaveChangesAsync();
```

> `FindAsync(start, 20)` скомпилируется (аргументы — `params object[]`), но упадёт во время выполнения с `ArgumentException`: типы значений не совпадут с типами ключа. Порядок аргументов `Find` берётся из `HasKey`.

> `chk_contract_start_date` и `chk_contract_end_date` требуют дат не позже сегодняшней. Контракт «с завтрашнего дня» база отвергнет с `DbUpdateException` (код `23514`). EF про `CHECK` не знает.

**Заезд с соблюдением всех `CHECK`.** У `race_entry` их полтора десятка, и они связаны между собой. Финишировавший заезд должен иметь `finish_position`, `total_time`, `best_lap`, круги ≥ 1 и `total_time >= best_lap * laps_completed`:

```csharp
var entry = new RaceEntry
{
    DriverId = 20, CarId = 82, TrackId = 17,
    RaceDate = DateOnly.FromDateTime(DateTime.Today),
    Status = "finished",
    GridPosition = 5, FinishPosition = 3,
    LapsCompleted = 50,
    BestLap = TimeSpan.FromSeconds(91.4),
    TotalTime = TimeSpan.FromMinutes(78)          // ≥ 91.4 с × 50 = 76 мин 10 с
};
```

Поставь `Status = "dnf"`, не убрав `FinishPosition`, и база ответит нарушением `chk_finish_position`: `(status = 'finished') = (finish_position IS NOT NULL)` даёт `false = true`.

Массовые операции без загрузки (EF Core 7+):

```csharp
// закрыть все открытые контракты неактивных команд
var today = DateOnly.FromDateTime(DateTime.Today);
int closed = await db.Contracts
    .Where(k => k.EndDate == null && !k.Team.IsActive)
    .ExecuteUpdateAsync(set => set.SetProperty(k => k.EndDate, today));
```

| Способ | Плюсы | Минусы |
|---|---|---|
| загрузить → изменить → `SaveChanges` | работает со связями, одна транзакция | лишний `SELECT` |
| `ExecuteUpdate` / `ExecuteDelete` | один SQL на всё | без change tracking |

> Внешние ключи у тебя без `ON DELETE` (`NO ACTION`): удалить команду, у которой есть машины или контракты, база не даст (`DbUpdateException`, код `23503`). Поэтому в примере удаляется только что созданная команда. Удали её **до** создания контракта или сначала удали контракт.

> `SaveChangesAsync` выполняет все накопленные изменения в одной транзакции: если одна вставка нарушит ограничение, не применится ни одна.

### Практика

1. Добавь машину новой команды и заезд на ней одним `SaveChangesAsync`. Проверь, что `CHECK` на `race_entry` проходят (или специально нарушь один и прочитай ошибку).
2. Поймай `DbUpdateException` при удалении команды, у которой есть машины, и выведи понятное сообщение по `PostgresException.SqlState` и `ConstraintName`.
3. Через `ExecuteUpdateAsync` пометь неактивными все команды, у которых нет ни одной машины после 2015 года.

## Урок 11. Доступ к данным через хранимую процедуру

Последний пункт: получить данные, выполняя только хранимую процедуру (функцию). Используем твои функции и процедуры из лабы 3.

В PostgreSQL процедура (`CREATE PROCEDURE`) не возвращает набор строк. Данные наружу отдают **табличные функции** (`RETURNS TABLE`), а процедуры сообщают о результате через `RAISE NOTICE` или `INOUT`-параметры. У тебя есть и то и другое.

**Табличная функция `fn_driver_season` в EF.** Класс под строку результата и `SqlQuery`:

```csharp
public class SeasonRow
{
    public string TrackName { get; set; } = "";
    public string CarModel { get; set; } = "";
    public short GridPosition { get; set; }
    public short? FinishPosition { get; set; }
    public string Status { get; set; } = "";
    public DateOnly RaceDate { get; set; }
}

public static async Task CallFunction(RacingContext db, int driverId, int year)
{
    var season = await db.Database
        .SqlQuery<SeasonRow>($"""
            SELECT track_name AS "TrackName", car_model AS "CarModel",
                   grid_position AS "GridPosition", finish_position AS "FinishPosition",
                   status AS "Status", race_date AS "RaceDate"
            FROM fn_driver_season({driverId}, {year})
            """)
        .ToListAsync();

    foreach (var r in season)
        Console.WriteLine($"{r.RaceDate}  {r.TrackName,-30} старт {r.GridPosition,2}  финиш {r.FinishPosition?.ToString() ?? r.Status}");
}
```

`SqlQuery<T>` (EF Core 8+) выполняет SQL и раскладывает столбцы по свойствам `T`.

> `{driverId}` внутри `$"..."` — **не** склейка строк. `SqlQuery` принимает `FormattableString` и превращает подстановки в параметры. Инъекции нет.

> Имена столбцов должны совпадать с именами свойств. PostgreSQL приводит неквотированные имена к нижнему регистру, поэтому алиасы в кавычках: `AS "TrackName"`.

**Многооператорная `fn_driver_career`** возвращает пары «показатель — значение»:

```csharp
public class MetricRow
{
    public string Metric { get; set; } = "";
    public string? Value { get; set; }
}

var career = await db.Database
    .SqlQuery<MetricRow>($"SELECT metric AS \"Metric\", value AS \"Value\" FROM fn_driver_career({736})")
    .ToListAsync();
```

`RAISE EXCEPTION 'Пилот % не найден'` из функции прилетит как `PostgresException`; текст в `e.MessageText`.

**Скалярная `fn_avg_speed`**: для простых типов EF ждёт столбец с именем `Value`, функция может вернуть `NULL`:

```csharp
var speed = await db.Database
    .SqlQuery<decimal?>($"SELECT fn_avg_speed({20}, {new DateOnly(1950, 5, 13)}) AS \"Value\"")
    .SingleAsync();
Console.WriteLine(speed is null ? "нет данных" : $"{speed} км/ч");
```

**Процедура `pr_disqualify`** меняет данные и печатает `RAISE NOTICE`. Вызовем в транзакции и откатим, чтобы не портить данные:

```csharp
public static async Task CallProcedure(RacingContext db, int driverId, DateOnly raceDate)
{
    await using var tx = await db.Database.BeginTransactionAsync();
    try
    {
        await db.Database.ExecuteSqlAsync($"CALL pr_disqualify({driverId}, {raceDate})");

        // смотрим результат внутри той же транзакции
        var trackId = await db.RaceEntries
            .Where(x => x.DriverId == driverId && x.RaceDate == raceDate)
            .Select(x => x.TrackId)
            .FirstAsync();
        var protocol = await db.RaceEntries
            .Where(re => re.RaceDate == raceDate && re.TrackId == trackId)
            .OrderBy(re => re.FinishPosition)
            .Select(re => new { re.DriverId, re.Status, re.FinishPosition })
            .ToListAsync();
        protocol.ForEach(Console.WriteLine);
    }
    catch (Npgsql.PostgresException e)
    {
        Console.WriteLine($"Процедура отказала: {e.MessageText}");
    }
    await tx.RollbackAsync();          // для сдачи замени на CommitAsync
    Console.WriteLine("Изменения откачены");
}
```

NOTICE `Перемещено N значений` напечатает обработчик из `Db.Create` (урок 8).

> Запросы после `CALL` идут через тот же контекст и, значит, в той же транзакции: они видят изменения процедуры, хотя в базе для других клиентов ничего ещё не поменялось. После `RollbackAsync` пропадут и изменения, и записи триггера аудита из лабы 3, если он включён.

| Задача | Метод |
|---|---|
| табличная функция → свой класс | `db.Database.SqlQuery<T>($"SELECT ... FROM f({x})")` |
| скалярная функция | `db.Database.SqlQuery<decimal?>($"SELECT f({x}) AS \"Value\"")` |
| функция → сущности + LINQ | `db.Set.FromSql($"SELECT * FROM f({x})").Where(...)` |
| процедура | `db.Database.ExecuteSqlAsync($"CALL p({x})")` |
| `RAISE NOTICE` | событие `NpgsqlConnection.Notice` |
| попробовать и откатить | `BeginTransactionAsync()` … `RollbackAsync()` |

Подробнее: [SQL Queries в EF Core](https://learn.microsoft.com/en-us/ef/core/querying/sql-queries).

### Практика

1. Вызови `fn_team_tree` через `SqlQuery<T>` и выведи дерево с отступами по `level`.
2. Вызови `pr_close_team` в транзакции с откатом и посмотри, какие NOTICE прилетят от рекурсивных вызовов.
3. (*) Сделай функцию `RETURNS SETOF driver` (пилоты с победами на трассе X), вызови её через `db.Drivers.FromSql(...)` и допиши `OrderBy`. Посмотри через `ToQueryString()`, как EF обернул SQL в подзапрос.

---

# Итог: структура проекта

```
Lab07/
├── Lab07.csproj
├── Program.cs
├── Db.cs
├── LinqToObjects.cs
├── LinqToJson.cs
├── LinqToDb.cs
├── Objects/
│   ├── Rows.cs
│   └── Loader.cs
└── Models/              ← сгенерировано dotnet ef
    ├── RacingContext.cs
    ├── Driver.cs, Car.cs, Team.cs, Track.cs
    └── RaceEntry.cs, Contract.cs
```

`Program.cs` целиком:

```csharp
using Lab07;
using Lab07.Objects;
using Npgsql;

var cs = Environment.GetEnvironmentVariable("LAB_DB")
         ?? throw new InvalidOperationException("Задай переменную LAB_DB");
await using var ds = NpgsqlDataSource.Create(cs);

Console.WriteLine("===== 1. LINQ to Objects =====");
var entries = await Loader.LoadEntries(ds);
var drivers = await Loader.LoadDrivers(ds);
var tracks = await Loader.LoadTracks(ds);
LinqToObjects.FiveQueries(entries, drivers, tracks);

Console.WriteLine("\n===== 2. LINQ to JSON =====");
var tracksJson = await LinqToJson.LoadTracks(ds);
LinqToJson.Save(tracksJson, "tracks.json");
LinqToJson.Read(tracksJson);
LinqToJson.Update(tracksJson);
LinqToJson.Add(tracksJson);
LinqToJson.Save(tracksJson, "tracks_updated.json");

Console.WriteLine("\n===== 3. LINQ к базе (EF Core) =====");
await using var db = Db.Create(cs);
await LinqToDb.SingleTable(db);
await LinqToDb.MultiTableJoin(db);
await LinqToDb.MultiTableNav(db);
await LinqToDb.Crud(db);
await LinqToDb.CallFunction(db, driverId: 657, year: 2000);
await LinqToDb.CallProcedure(db, driverId: 20, raceDate: new DateOnly(1950, 5, 13));
```

`Crud`, `CallFunction`, `CallProcedure`, `SeasonRow` и `MetricRow` из уроков 10–11 положи в `LinqToDb.cs`.

# Финальное задание

Сделай второй проект `Lab07.Extra` на других таблицах, без копирования кода уроков:

- LINQ to Objects: коллекции `CarRow` (все столбцы `car`) и `ContractRow`; пять запросов, покрывающих все ключевые слова, в том числе группировка машин по классу и десятилетию и групповое соединение команд с контрактами.
- LINQ to JSON: документ «пилот → контракты → команды → победы пилота за каждую команду» для 20 самых титулованных пилотов; чтение (пилоты, побеждавшие за три и более команды), обновление (добавить каждому поле «лучший сезон»), добавление (новый контракт пилоту); результат в файл.
- EF Core: однотабличный запрос по `car`, многотабличный «команда — дочерние команды — машины — победы за последние 10 лет», добавление/изменение/удаление контракта (составной ключ), получение данных только через `fn_driver_career` и `fn_team_tree`.
- Вывести SQL для каждого EF-запроса через `ToQueryString()` или `LogTo`.

# Шпаргалка

```csharp
// синтаксис запросов
from x in xs
join y in ys on new { x.A, x.B } equals new { y.A, y.B } [into g]   // составной ключ
let v = ...
where cond
group x by key [into g]
orderby a ascending, b descending
select new { ... }

// Npgsql: типы
r.GetInt16(i)  (smallint)   r.GetTimeSpan(i)  (interval)   r.GetFieldValue<DateOnly>(i)  (date)
r.IsDBNull(i) ? null : ...
ts.ToString(@"hh\:mm\:ss\.fff")   TimeSpan.FromSeconds(x)   ts.TotalSeconds

// JsonNode
var arr = JsonNode.Parse(json)!.AsArray();
node["k"]!.GetValue<double>()   node["k"]?.GetValue<string>() ?? "-"   node["k"] = 1.5m
arr.Add(new JsonObject { ["k"] = "v" })

// EF Core
dotnet ef dbcontext scaffold "<cs>" Npgsql.EntityFrameworkCore.PostgreSQL -o Models -c RacingContext --no-onconfiguring --table ...
await db.RaceEntries.Where(...).ToListAsync();     query.ToQueryString();
await db.Contracts.FindAsync(driverId, startDate);  // составной ключ, порядок как в HasKey
db.Add(x); x.Prop = v; db.Remove(x); await db.SaveChangesAsync();
db.Database.SqlQuery<Row>($"SELECT a AS \"A\" FROM fn({x})")
db.Database.SqlQuery<decimal?>($"SELECT fn({x}) AS \"Value\"")
await db.Database.ExecuteSqlAsync($"CALL pr({x})");
((NpgsqlConnection)db.Database.GetDbConnection()).Notice += (_, e) => Console.WriteLine(e.Notice.MessageText);
await using var tx = await db.Database.BeginTransactionAsync(); ... await tx.RollbackAsync();
```

# Источники и что почитать дальше

**Официальная документация**
- [LINQ (C#)](https://learn.microsoft.com/en-us/dotnet/csharp/linq/) — введение и синтаксис запросов.
- [Query keywords](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/keywords/query-keywords) — все ключевые слова выражения запроса; по нему удобно сверить покрытие пункта 1.
- [Standard query operators](https://learn.microsoft.com/en-us/dotnet/csharp/linq/standard-query-operators/) — методы LINQ, которых нет в синтаксисе запросов.
- [Use a JSON DOM (JsonNode)](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-dom) — `JsonNode`, `JsonObject`, `JsonArray`.
- [LINQ to XML overview](https://learn.microsoft.com/en-us/dotnet/standard/linq/linq-xml-overview) — если делаешь вариант с XML.
- [Entity Framework Core](https://learn.microsoft.com/en-us/ef/core/) — основы EF Core.
- [Scaffolding](https://learn.microsoft.com/en-us/ef/core/managing-schemas/scaffolding/) — генерация моделей по базе, опция `--table`.
- [SQL Queries](https://learn.microsoft.com/en-us/ef/core/querying/sql-queries) — `FromSql`, `SqlQuery`, `ExecuteSql`.
- [Npgsql EF Core provider](https://www.npgsql.org/efcore/) — особенности PostgreSQL в EF, отображение `interval` и `date`.

**Курсы**
- [Tour of C#](https://learn.microsoft.com/en-us/dotnet/csharp/tour-of-csharp/) — если нужно подтянуть сам язык.
