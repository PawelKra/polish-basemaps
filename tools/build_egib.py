#!/usr/bin/env python3
"""Buduje data/egib.json: powiatowe usługi WFS EGiB, które RustGIS potrafi wczytać.

Źródło: eksport CSV z Ewidencji zbiorów i usług danych przestrzennych GUGiK
(EZiUDP, https://integracja.gugik.gov.pl/eziudp/), zapisany w
data/zrodla/eziudp_powiaty_wfs.csv:

  curl -o data/zrodla/eziudp_powiaty_wfs.csv \
    'https://integracja.gugik.gov.pl/eziudp/api.php?rodzaj=powiaty&uslugaTyp=WFS&format=csv'

Dla każdego powiatu pyta RustGIS (`rustgis-cli ... service.layers`), czy usługa
oddaje GeoJSON, i wybiera warstwy działek i budynków. Powiaty bez GeoJSON trafiają
do pliku z pustymi nazwami warstw, żeby wtyczka mogła o nich rzetelnie powiedzieć.

  python tools/build_egib.py
"""

import concurrent.futures as cf
import csv
import json
import pathlib
import re
import sys

from rustgis_compat import check

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "zrodla" / "eziudp_powiaty_wfs.csv"
OUT = ROOT / "data" / "egib.json"


def pick(layers, pattern):
    found = [name for name in layers if re.search(pattern, name, re.I)]
    # Krótsza nazwa to zwykle warstwa główna (ewns:dzialki, nie ewns:dzialki_opisy)
    return min(found, key=len) if found else ""


def main():
    with open(SOURCE, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f, delimiter=";") if r["Zbiór"].startswith("Ewidencja Gruntów")]

    def one(row):
        entry = {"url": row["Usługa Pobierania"].strip(), "type": "WFS"}
        res = check(entry, timeout=90)
        ok = res["rg_status"] == "ok"
        dzialki = pick(res["rg_layers"], r"dzia[lł]k") if ok else ""
        budynki = pick(res["rg_layers"], r"budyn") if ok else ""
        return {
            "teryt": row["TERYT"],
            "obszar": row["Obszar"],
            "url": entry["url"],
            "dzialki": dzialki,
            "budynki": budynki,
            # Zapytania GetFeature w GeoJSON, jakie składa RustGIS; wtyczka dokleja do nich BBOX
            "dzialki_getfeature": res["rg_offers"].get(dzialki, "") if dzialki else "",
            "budynki_getfeature": res["rg_offers"].get(budynki, "") if budynki else "",
            "uwagi": res["rg_notes"],
        }

    out = []
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        for i, item in enumerate(pool.map(one, rows), 1):
            out.append(item)
            print(f"[{i}/{len(rows)}] {item['teryt']} {item['dzialki'] or '-':<16} {item['obszar']}",
                  file=sys.stderr, flush=True)
    out.sort(key=lambda r: r["teryt"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sum(1 for r in out if r['dzialki'])} z {len(out)} powiatów z GeoJSON")


if __name__ == "__main__":
    main()
