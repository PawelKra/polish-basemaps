#!/usr/bin/env python3
"""Sprawdza, które usługi z raportu walidacji RustGIS potrafi wyświetlić.

RustGIS rysuje WMS i WMTS tylko w Web Mercatorze (EPSG:3857), a WFS tylko
z wyjściem GeoJSON. Dla każdej usługi ze statusem ok* wywołuje
`rustgis-cli run --cmd service.layers=...` i zapisuje liczbę warstw,
które RustGIS przyjmuje, oraz jego uwagi.

  python rustgis_compat.py --report ../raport/walidacja.json --out ../raport/rustgis.json
"""

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys


def check(entry, timeout):
    params = json.dumps({"url": entry["url"], "type": entry["type"].lower()})
    try:
        proc = subprocess.run(["rustgis-cli", "run", "--cmd", f"service.layers={params}"],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"rg_status": "timeout", "rg_count": 0, "rg_notes": "", "rg_layers": [], "rg_offers": {}}
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        return {"rg_status": "error", "rg_count": 0, "rg_notes": err[-1][:300] if err else "",
                "rg_layers": [], "rg_offers": {}}
    count = out.get("count", 0)
    layers = out.get("layers", [])
    return {"rg_status": "ok" if count else "none", "rg_count": count,
            "rg_notes": " | ".join(out.get("notes", [])),
            "rg_layers": [l.get("name") for l in layers],
            # Adres, którym RustGIS pobrałby warstwę (GetMap, GetTile albo GetFeature)
            "rg_offers": {l.get("name"): (l.get("offer") or {}).get("url", "") for l in layers}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="walidacja.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)
    todo = [r for r in report if r["status"].startswith("ok")]

    results = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check, r, args.timeout): r for r in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            r = futures[fut]
            results[r["id"]] = fut.result()
            print(f"[{i}/{len(todo)}] {results[r['id']]['rg_status']:<8} {r['id']:<9} {r['name'][:60]}",
                  file=sys.stderr, flush=True)

    merged = [{**r, **results.get(r["id"], {"rg_status": "skipped", "rg_count": 0,
                                             "rg_notes": "", "rg_layers": []})}
              for r in report]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
