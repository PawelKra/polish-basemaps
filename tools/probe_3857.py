#!/usr/bin/env python3
"""Sprawdza, czy usługi WMS bez ogłoszonego EPSG:3857 i tak oddają mapę w 3857.

RustGIS przyjmuje przez service.add tylko WMS ogłaszające EPSG:3857. Część
serwerów (np. ArcGIS Server GUGiK) przelicza jednak GetMap do 3857, choć tego
nie ogłasza; takie usługi można dodać szablonem kafli przez map.addTiles.

Dla każdej usługi WMS z raportu rustgis.json, której RustGIS nie przyjął,
pobiera Capabilities, a dla każdej nazwanej warstwy wysyła GetMap w EPSG:3857
(kafel 256 px) w kilku punktach Polski i w dwóch skalach. Kafel uznaje za
treść, gdy jest obrazem większym niż --min-bytes (puste PNG mają < 1 kB).

  python probe_3857.py --report ../raport/rustgis.json --out ../raport/probe_3857.json
"""

import argparse
import concurrent.futures as cf
import json
import math
import sys
import urllib.parse
import xml.etree.ElementTree as ET

from validate_capabilities import USER_AGENT, caps_url, descendants, fetch, first, local, text

# Kraków, Warszawa, Poznań
POINTS = [(19.94, 50.06), (21.01, 52.23), (16.93, 52.41)]
ZOOMS = [12, 16]


def tile_bbox(lon, lat, z):
    """Granice kafla XYZ zawierającego punkt, w metrach EPSG:3857."""
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    size = 2 * math.pi * 6378137 / n
    minx = -math.pi * 6378137 + x * size
    maxy = math.pi * 6378137 - y * size
    return minx, maxy - size, minx + size, maxy


def getmap_template(base_url, layer, fmt):
    parts = urllib.parse.urlsplit(base_url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in {"service", "request", "version", "layers", "styles", "crs",
                                  "srs", "bbox", "width", "height", "format", "transparent"}]
    query += [("SERVICE", "WMS"), ("VERSION", "1.3.0"), ("REQUEST", "GetMap"),
              ("LAYERS", layer), ("STYLES", ""), ("CRS", "EPSG:3857"), ("WIDTH", "256"),
              ("HEIGHT", "256"), ("FORMAT", fmt), ("TRANSPARENT", "TRUE")]
    q = urllib.parse.urlencode(query, safe=":/,")
    return urllib.parse.urlunsplit(parts._replace(query=q)) + "&BBOX={bbox-epsg-3857}"


def probe_layer(template, timeout, min_bytes):
    hits = []
    for z in ZOOMS:
        for lon, lat in POINTS:
            bbox = ",".join(f"{v:.2f}" for v in tile_bbox(lon, lat, z))
            url = template.replace("{bbox-epsg-3857}", bbox)
            try:
                _, _, ctype, body = fetch(url, timeout)
            except Exception as exc:  # noqa: BLE001
                hits.append({"z": z, "point": [lon, lat], "error": type(exc).__name__})
                continue
            is_image = ctype.startswith("image/") and body[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb")
            hits.append({"z": z, "point": [lon, lat], "image": is_image, "bytes": len(body),
                         "content": is_image and len(body) >= min_bytes,
                         "error": "" if is_image else body[:200].decode("utf-8", "replace")})
    return hits


def probe_service(entry, timeout, min_bytes, max_layers):
    try:
        _, _, _, body = fetch(caps_url(entry["url"], "WMS", "1.3.0"), timeout)
        root = ET.fromstring(body)
    except Exception as exc:  # noqa: BLE001
        return {"id": entry["id"], "error": f"capabilities: {exc}", "layers": []}
    formats = [text(f) for gm in descendants(root, "GetMap") for f in descendants(gm, "Format")]
    fmt = "image/png" if "image/png" in formats else (formats[0] if formats else "image/png")
    layers = []
    for lyr in descendants(root, "Layer"):
        name = text(first(lyr, "Name"))
        if name:
            layers.append({"name": name, "title": text(first(lyr, "Title"))})
    out = []
    for lyr in layers[:max_layers]:
        template = getmap_template(entry["url"], lyr["name"], fmt)
        hits = probe_layer(template, timeout, min_bytes)
        out.append({**lyr, "template": template,
                    "works": any(h.get("image") for h in hits),
                    "content": any(h.get("content") for h in hits),
                    "content_zooms": sorted({h["z"] for h in hits if h.get("content")}),
                    "hits": hits})
    return {"id": entry["id"], "name": entry["name"], "url": entry["url"], "format": fmt,
            "layer_total": len(layers), "layers": out, "error": ""}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="rustgis.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", help="lista id rozdzielona przecinkami (domyślnie: WMS odrzucone przez RustGIS)")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--min-bytes", type=int, default=1500)
    ap.add_argument("--max-layers", type=int, default=20)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(args.report, encoding="utf-8") as f:
        report = json.load(f)
    if args.ids:
        wanted = set(args.ids.split(","))
        todo = [r for r in report if r["id"] in wanted]
    else:
        todo = [r for r in report if r["type"] == "WMS" and r["status"].startswith("ok")
                and r.get("rg_status") == "none"]

    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(probe_service, r, args.timeout, args.min_bytes, args.max_layers): r for r in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            res = fut.result()
            results.append(res)
            ok = sum(1 for l in res["layers"] if l["content"])
            print(f"[{i}/{len(todo)}] {res['id']:<8} warstw z treścią {ok}/{len(res['layers'])} "
                  f"{res.get('name', '')[:50]} {res['error'][:60]}", file=sys.stderr, flush=True)

    order = {r["id"]: n for n, r in enumerate(todo)}
    results.sort(key=lambda r: order[r["id"]])
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
