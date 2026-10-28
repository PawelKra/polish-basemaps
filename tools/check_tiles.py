#!/usr/bin/env python3
"""Pobiera kafle z każdego szablonu katalogu (src/catalog.rs) i sprawdza, czy są obrazami z treścią.

Dla każdej pozycji próbuje kilku punktów Polski na kilku zoomach z przedziału
[min_zoom, max_zoom] i zapisuje największy kafel do --out-dir, żeby dało się
go obejrzeć. Kafel pusty (jednolity) ma zwykle poniżej 1,5 kB.

  python tools/check_tiles.py --out-dir /tmp/kafle
"""

import argparse
import concurrent.futures as cf
import json
import math
import pathlib
import re
import sys

from validate_capabilities import fetch

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTRY = re.compile(r'Entry \{\s*id: "([^"]+)",\s*name: "([^"]+)",\s*url: "([^"]+)",.*?min_zoom: (\d+),\s*max_zoom: (\d+)', re.S)

# Kraków, Warszawa, Wrocław, Zakopane
POINTS = [(19.94, 50.06), (21.01, 52.23), (17.03, 51.11), (19.95, 49.30)]


def tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def bbox(x, y, z):
    size = 2 * math.pi * 6378137 / 2 ** z
    minx = -math.pi * 6378137 + x * size
    maxy = math.pi * 6378137 - y * size
    return f"{minx:.2f},{maxy - size:.2f},{minx + size:.2f},{maxy:.2f}"


def check(entry, timeout, min_bytes, out_dir):
    eid, name, url, minz, maxz = entry
    best = {"bytes": 0}
    errors = []
    # Dwa zoomy z dozwolonego przedziału: rzadkie punkty widać w małej skali, plany dopiero w dużej
    zooms = sorted({min(max(z, minz), maxz) for z in (9, 13, 17)})
    for z, (lon, lat) in ((z, p) for z in zooms for p in POINTS):
        x, y = tile(lon, lat, z)
        u = (url.replace("{bbox-epsg-3857}", bbox(x, y, z))
             .replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y)))
        try:
            _, _, ctype, body = fetch(u, timeout)
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__ + ": " + str(exc)[:80])
            continue
        if not ctype.startswith("image/"):
            errors.append(body[:160].decode("utf-8", "replace").replace("\n", " "))
            continue
        if len(body) > best["bytes"]:
            ext = "jpg" if "jpeg" in ctype else "png"
            best = {"bytes": len(body), "point": [lon, lat], "z": z, "file": f"{eid}.{ext}", "data": body}
    if best["bytes"]:
        (out_dir / best["file"]).write_bytes(best.pop("data"))
    status = "ok" if best["bytes"] >= min_bytes else ("pusty" if best["bytes"] else "błąd")
    return {"id": eid, "name": name, "status": status, **best, "errors": errors}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--min-bytes", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = [(m[0], m[1], m[2], int(m[3]), int(m[4]))
               for m in ENTRY.findall((ROOT / "src" / "catalog.rs").read_text(encoding="utf-8"))]
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda e: check(e, args.timeout, args.min_bytes, out_dir), entries))
    for r in results:
        print(f"{r['status']:<6} {r['id']:<24} {r['bytes']:>7} B  {(r['errors'] or [''])[0][:90]}")
    (out_dir / "wyniki.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r["id"] for r in results if r["status"] != "ok"]
    print(f"{len(results) - len(bad)}/{len(results)} z treścią; do sprawdzenia: {', '.join(bad) or 'brak'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
