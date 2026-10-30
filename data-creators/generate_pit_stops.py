#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор пит-стопов для лабы 5 (JSON).

Читает ../data/race_entry.csv и пишет ../data/pit_stops.json — массив
{"driver_id", "race_date", "pit_stops": [{"lap", "duration_s", "tyre"}, ...]}
по одному объекту на каждый заезд. (driver_id, race_date) — первичный ключ
race_entry, по нему документ сопоставляется со строкой таблицы.

В базу ничего не вставляет: столбец и загрузку файла делаешь сам.

Правила:
  * 1–3 стопа, но не больше пройденных кругов; у заездов с 0 кругов
    (все dns и часть dnf) массив пустой;
  * i-й из n стопов попадает в i-ю часть дистанции, поэтому круги идут
    по возрастанию и не повторяются;
  * до 1990 года стоп длится 12–37 с, позже 2–4.5 с;
  * шины в основном сухие, примерно каждая десятая — intermediate или wet.
"""

import argparse
import csv
import json
import os
import random

TYRES = ["soft", "medium", "hard", "intermediate", "wet"]
TYRE_WEIGHTS = [30, 30, 30, 6, 4]


def pit_stops(laps, year, rnd):
    n = min(rnd.randint(1, 3), laps)
    stops = []
    for i in range(1, n + 1):
        lo = (i - 1) * laps // n
        hi = i * laps // n
        stops.append({
            "lap": lo + 1 + rnd.randrange(hi - lo),
            "duration_s": round(rnd.uniform(12, 37) if year < 1990 else rnd.uniform(2, 4.5), 1),
            "tyre": rnd.choices(TYRES, TYRE_WEIGHTS)[0],
        })
    return stops


def main():
    p = argparse.ArgumentParser(description="Генератор пит-стопов (JSON)")
    p.add_argument("--data", default=None, help="папка с race_entry.csv (по умолчанию ../data)")
    p.add_argument("--out", default=None, help="куда писать (по умолчанию <data>/pit_stops.json)")
    p.add_argument("--seed", type=int, default=42, help="зерно случайных чисел")
    args = p.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = args.data or os.path.join(os.path.dirname(here), "data")
    out_path = args.out or os.path.join(data_dir, "pit_stops.json")
    rnd = random.Random(args.seed)

    docs = []
    with open(os.path.join(data_dir, "race_entry.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            docs.append({
                "driver_id": int(row["driver_id"]),
                "race_date": row["race_date"],
                "pit_stops": pit_stops(int(row["laps_completed"]), int(row["race_date"][:4]), rnd),
            })

    # по объекту на строку: файл и читать можно, и весит немного
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("[\n")
        f.write(",\n".join(json.dumps(d, ensure_ascii=False) for d in docs))
        f.write("\n]\n")

    print("Записано заездов: %d -> %s" % (len(docs), out_path))


if __name__ == "__main__":
    main()
