#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор технических характеристик машин для лабы 5 (JSON).

Читает ../data/car.csv и пишет ../data/car_specs.json — массив
{"car_id", "specs": {...}} по одному объекту на машину.
В базу ничего не вставляет: столбец и загрузку файла делаешь сам.

Форма specs зависит от класса и эпохи, поэтому документы разные:
  * engine — всегда: layout, cylinders, displacement_l, turbo;
    hybrid {ers_kw} только у гибридов (формула с 2009, гиперкары);
  * aero — только у формул и гиперкаров; drs только у формул с 2011;
  * tyres — массив составов шин, у stock один ["slick"];
  * sponsors — массив {name, share}; у машин до 1968 ключа нет вовсе
    (в F1 тогда не было коммерческих спонсоров);
  * top_speed_kmh и homologated — всегда.
Мощность и вес берутся из car.csv, двигатель подбирается под эпоху.
"""

import argparse
import csv
import json
import os
import random

SPONSORS = ["Petronas", "Shell", "Red Bull", "Marlboro", "Mobil 1", "Pirelli", "DHL",
            "Aramco", "Oracle", "Santander", "Martini", "Castrol", "Rolex", "Heineken",
            "Monster Energy", "Michelin", "Bridgestone", "Vodafone", "AWS", "Crypto.com"]


def engine(cls, year, hp, rnd):
    """(layout, cylinders, displacement_l, turbo, ers_kw или None)"""
    if cls == "formula":
        if year >= 1990 and hp < 650:  # младшие формулы
            return rnd.choice([("I4", 4, 2.0, False), ("I4", 4, 1.6, True), ("V6", 6, 3.4, True)]) + (None,)
        if year >= 2014:
            return ("V6", 6, 1.6, True, 120)
        if year >= 2006:
            return ("V8", 8, 2.4, False, 60 if year >= 2009 else None)
        if year >= 1989:
            return rnd.choice([("V10", 10, 3.0, False), ("V12", 12, 3.5, False), ("V8", 8, 3.5, False)]) + (None,)
        if year >= 1977:
            return rnd.choice([("V6", 6, 1.5, True), ("I4", 4, 1.5, True), ("V8", 8, 3.0, False)]) + (None,)
        if year >= 1966:
            return rnd.choice([("V8", 8, 3.0, False), ("V12", 12, 3.0, False), ("F12", 12, 3.0, False)]) + (None,)
        return rnd.choice([("I4", 4, 2.5, False), ("I6", 6, 2.5, False), ("V8", 8, 1.5, False),
                           ("V12", 12, 1.5, False)]) + (None,)
    if cls == "hypercar":
        return rnd.choice([("V6", 6, 2.6, True), ("V8", 8, 3.2, True), ("V8", 8, 4.0, True)]) + (200,)
    if cls == "gt":
        return rnd.choice([("V8", 8, 4.0, True), ("F6", 6, 4.2, False), ("V8", 8, 6.2, False),
                           ("V10", 10, 5.2, False)]) + (None,)
    if cls == "touring":
        return ("I4", 4, 2.0, True, None)
    return ("V8", 8, 5.8, False, None)  # stock


def tyres(cls, year):
    if cls == "stock":
        return ["slick"]
    if cls == "formula" and year >= 2011:
        return ["soft", "medium", "hard", "intermediate", "wet"]
    return ["dry", "wet"]


def specs(row, rnd):
    cls = row["car_class"]
    year = int(row["season_year"])
    hp = int(row["horsepower"])
    kg = float(row["weight_kg"])
    layout, cyl, disp, turbo, ers_kw = engine(cls, year, hp, rnd)

    eng = {"layout": layout, "cylinders": cyl, "displacement_l": disp, "turbo": turbo}
    if ers_kw:
        eng["hybrid"] = {"ers_kw": ers_kw}

    doc = {"engine": eng}
    if cls in ("formula", "hypercar"):
        aero = {"downforce": rnd.choice(["low", "medium", "high"])}
        if cls == "formula" and year >= 2011:
            aero["drs"] = True
        doc["aero"] = aero
    doc["tyres"] = tyres(cls, year)
    if year >= 1968:
        names = rnd.sample(SPONSORS, rnd.randint(0, 4))
        doc["sponsors"] = [{"name": n, "share": round(rnd.uniform(0.05, 0.3), 2)} for n in names]
    # скорость растёт с удельной мощностью, разброс ±5%
    doc["top_speed_kmh"] = round((200 + 110 * hp / kg) * rnd.uniform(0.95, 1.05))
    doc["homologated"] = rnd.random() > 0.03
    return doc


def main():
    p = argparse.ArgumentParser(description="Генератор характеристик машин (JSON)")
    p.add_argument("--data", default=None, help="папка с car.csv (по умолчанию ../data)")
    p.add_argument("--out", default=None, help="куда писать (по умолчанию <data>/car_specs.json)")
    p.add_argument("--seed", type=int, default=42, help="зерно случайных чисел")
    args = p.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = args.data or os.path.join(os.path.dirname(here), "data")
    out_path = args.out or os.path.join(data_dir, "car_specs.json")
    rnd = random.Random(args.seed)

    with open(os.path.join(data_dir, "car.csv"), newline="", encoding="utf-8") as f:
        docs = [{"car_id": int(row["car_id"]), "specs": specs(row, rnd)} for row in csv.DictReader(f)]

    # по объекту на строку: файл и читать можно, и весит немного
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("[\n")
        f.write(",\n".join(json.dumps(d, ensure_ascii=False) for d in docs))
        f.write("\n]\n")

    print("Записано машин: %d -> %s" % (len(docs), out_path))


if __name__ == "__main__":
    main()
