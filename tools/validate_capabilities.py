#!/usr/bin/env python3
"""Walidacja katalogu usług WMS/WMTS/WFS przez zapytanie GetCapabilities.

Dla każdej pozycji katalogu:
  - buduje adres GetCapabilities z adresu bazowego (usuwa parametry OWS
    zaszyte w URL, np. pełne zapytanie GetMap),
  - pobiera dokument, w razie potrzeby próbuje starszych wersji protokołu,
  - rozróżnia błędy sieciowe, HTTP, certyfikatu TLS, ServiceException
    i odpowiedzi, które nie są dokumentem Capabilities (np. HTML),
  - dla adresów http:// sprawdza, czy działa wariant https://,
  - zbiera tytuł usługi, liczbę warstw, obsługę EPSG:2180 / EPSG:3857
    oraz adres operacji (GetMap / GetFeature / GetTile) ogłaszany przez serwer,
  - dla WMTS sprawdza, czy warstwa z katalogu istnieje w Capabilities.

Tylko biblioteka standardowa. Przykład:
  python validate_capabilities.py --catalog ../data/katalog_uslug.json --out-dir ../raport
"""

import argparse
import collections
import concurrent.futures as cf
import csv
import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = "polskie-uslugi-validator/0.1"
MAX_BYTES = 64 * 1024 * 1024

# Wersje protokołu w kolejności prób
VERSIONS = {
    "WMS": ["1.3.0", "1.1.1"],
    "WFS": ["2.0.0", "1.1.0", "1.0.0"],
    "WMTS": ["1.0.0"],
}

# Parametry OWS, które nie należą do adresu bazowego usługi
OWS_PARAMS = {
    "service", "request", "version", "acceptversions", "layers", "layer", "styles",
    "style", "bbox", "crs", "srs", "format", "width", "height", "transparent",
    "exceptions", "bgcolor", "typename", "typenames", "outputformat",
    "tilematrixset", "tilematrix", "tilerow", "tilecol", "query_layers",
    "info_format", "i", "j", "x", "y",
}

CAPS_ROOTS = {
    "WMS": {"WMS_Capabilities", "WMT_MS_Capabilities"},
    "WFS": {"WFS_Capabilities"},
    "WMTS": {"Capabilities"},
}
EXCEPTION_ROOTS = {"ServiceExceptionReport", "ExceptionReport"}

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def children(el, name):
    return [c for c in el if local(c.tag) == name]


def first(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def descendants(el, name):
    return [d for d in el.iter() if local(d.tag) == name]


def text(el):
    return (el.text or "").strip() if el is not None else ""


def caps_url(url, service_type, version):
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in OWS_PARAMS]
    query += [("SERVICE", service_type), ("REQUEST", "GetCapabilities")]
    if service_type == "WFS" and version == "2.0.0":
        query.append(("ACCEPTVERSIONS", version))
    query.append(("VERSION", version))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def fetch(url, timeout, verify=True):
    """Zwraca (kod HTTP, końcowy URL, content-type, treść)."""
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        body = resp.read(MAX_BYTES + 1)
        return resp.status, resp.geturl(), resp.headers.get("Content-Type", ""), body


def classify_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "http_error", f"HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "ssl_invalid", str(reason.verify_message or reason)
    if isinstance(reason, ssl.SSLError):
        return "ssl_error", str(reason)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout", "timeout"
    if isinstance(reason, socket.gaierror):
        return "dns_error", str(reason)
    return "conn_error", str(reason)


def parse_wms(root, info):
    service = first(root, "Service")
    info["title"] = text(first(service, "Title")) if service is not None else ""
    layers = [l for l in descendants(root, "Layer") if first(l, "Name") is not None]
    info["layer_count"] = len(layers)
    crs = {text(c).upper() for c in descendants(root, "CRS") + descendants(root, "SRS")}
    info["crs_2180"] = "EPSG:2180" in crs
    info["crs_3857"] = "EPSG:3857" in crs
    for gm in descendants(root, "GetMap"):
        for res in descendants(gm, "OnlineResource"):
            info["op_url"] = res.get(XLINK_HREF, "")
            break
        break


def ows_operation_url(root, op_name):
    for op in descendants(root, "Operation"):
        if op.get("name") == op_name:
            for get in descendants(op, "Get"):
                return get.get(XLINK_HREF, "")
    return ""


def parse_wfs(root, info):
    ident = first(root, "ServiceIdentification")
    if ident is None:
        ident = first(root, "Service")
    info["title"] = text(first(ident, "Title")) if ident is not None else ""
    fts = descendants(root, "FeatureType")
    info["layer_count"] = len(fts)
    crs = set()
    for ft in fts:
        for name in ("DefaultCRS", "OtherCRS", "DefaultSRS", "OtherSRS", "SRS"):
            for c in children(ft, name):
                crs.add(text(c).upper())
    info["crs_2180"] = any(c.endswith(("EPSG:2180", "EPSG::2180", "EPSG/0/2180")) for c in crs)
    info["crs_3857"] = any(c.endswith(("EPSG:3857", "EPSG::3857", "EPSG/0/3857")) for c in crs)
    info["op_url"] = ows_operation_url(root, "GetFeature")
    if not info["op_url"]:
        for gf in descendants(root, "GetFeature"):
            for get in descendants(gf, "Get"):
                info["op_url"] = get.get("onlineResource", "")
                break
            break


def parse_wmts(root, info, wanted_layer):
    ident = first(root, "ServiceIdentification")
    info["title"] = text(first(ident, "Title")) if ident is not None else ""
    contents = first(root, "Contents")
    layers = children(contents, "Layer") if contents is not None else []
    info["layer_count"] = len(layers)
    ids = [text(first(l, "Identifier")) for l in layers]
    crs = set()
    tms_ids = []
    if contents is not None:
        for tms in children(contents, "TileMatrixSet"):
            tms_ids.append(text(first(tms, "Identifier")))
            crs.add(text(first(tms, "SupportedCRS")).upper())
    info["crs_2180"] = any(c.endswith(("EPSG:2180", "EPSG::2180")) for c in crs)
    info["crs_3857"] = any(c.endswith(("EPSG:3857", "EPSG::3857")) for c in crs)
    info["tile_matrix_sets"] = ";".join(tms_ids)
    info["op_url"] = ows_operation_url(root, "GetTile")
    if wanted_layer and wanted_layer not in ids:
        info["warnings"].append(f"brak warstwy '{wanted_layer}' (są: {', '.join(ids[:10])})")


def try_service(entry, base_url, timeout, verify):
    """Jedna próba pełnej walidacji dla danego adresu bazowego."""
    stype = entry["type"]
    last = {"status": "conn_error", "detail": ""}
    for version in VERSIONS[stype]:
        url = caps_url(base_url, stype, version)
        t0 = time.monotonic()
        try:
            code, final_url, ctype, body = fetch(url, timeout, verify)
        except Exception as exc:  # noqa: BLE001 - klasyfikujemy każdy błąd sieci
            status, detail = classify_error(exc)
            # Błąd sieci/TLS nie zależy od wersji protokołu
            return {"status": status, "detail": detail, "request_url": url}
        elapsed = round(time.monotonic() - t0, 2)
        info = {"request_url": url, "final_url": final_url, "http_code": code,
                "elapsed_s": elapsed, "bytes": len(body), "version": version,
                "warnings": []}
        if len(body) > MAX_BYTES:
            return {**info, "status": "too_large", "detail": f">{MAX_BYTES} B"}
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            snippet = body[:120].decode("utf-8", "replace").replace("\n", " ")
            last = {**info, "status": "not_xml", "detail": f"{ctype}; {exc}; {snippet}"}
            continue
        rname = local(root.tag)
        if rname in EXCEPTION_ROOTS:
            msg = " ".join(t.strip() for t in root.itertext() if t.strip())[:300]
            last = {**info, "status": "service_exception", "detail": msg}
            continue
        if rname not in CAPS_ROOTS[stype]:
            last = {**info, "status": "not_capabilities", "detail": f"root <{rname}>"}
            continue
        if stype == "WMS":
            parse_wms(root, info)
        elif stype == "WFS":
            parse_wfs(root, info)
        else:
            parse_wmts(root, info, entry.get("layer", ""))
        if info.get("op_url", "").startswith("http://") and base_url.startswith("https://"):
            info["warnings"].append("serwer ogłasza operację po http://")
        return {**info, "status": "ok", "detail": ""}
    return last


class HostLimiter:
    """Ogranicza liczbę równoległych zapytań do jednego hosta."""

    def __init__(self, per_host):
        self.per_host = per_host
        self.lock = threading.Lock()
        self.sems = {}

    def get(self, url):
        host = urllib.parse.urlsplit(url).hostname or ""
        with self.lock:
            if host not in self.sems:
                self.sems[host] = threading.Semaphore(self.per_host)
            return self.sems[host]


def validate(entry, timeout, limiter):
    url = entry["url"].strip()
    with limiter.get(url):
        result = try_service(entry, url, timeout, verify=True)
        if result["status"] == "ssl_invalid":
            # Sprawdzamy, czy usługa działa poza samym certyfikatem
            retry = try_service(entry, url, timeout, verify=False)
            if retry["status"] == "ok":
                retry["status"] = "ok_ssl_invalid"
                retry["detail"] = result["detail"]
            result = retry if retry["status"] == "ok_ssl_invalid" else result
        https_ok = None
        if url.startswith("http://"):
            https_url = "https://" + url[len("http://"):]
            https_ok = try_service(entry, https_url, timeout, verify=True)["status"] == "ok"
    warnings = result.pop("warnings", [])
    if result["status"] == "ok" and warnings:
        result["status"] = "ok_warn"
    return {
        "id": entry["id"], "type": entry["type"], "level": entry.get("level", ""),
        "source": entry["source"], "name": entry["name"], "url": url,
        "https_ok": https_ok, "warnings": " | ".join(warnings), **result,
    }


FIELDS = ["id", "type", "level", "status", "detail", "warnings", "source", "name", "url",
          "https_ok", "version", "http_code", "elapsed_s", "bytes", "title", "layer_count",
          "crs_2180", "crs_3857", "tile_matrix_sets", "op_url", "final_url", "request_url"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", required=True, help="katalog_uslug.json")
    ap.add_argument("--out-dir", required=True, help="katalog na raport (JSON i CSV)")
    ap.add_argument("--type", action="append", choices=["WMS", "WFS", "WMTS"], help="filtr typu, można powtarzać")
    ap.add_argument("--level", choices=["krajowe", "powiat"], help="filtr poziomu")
    ap.add_argument("--ids", help="lista id rozdzielona przecinkami, np. wms-37,wmts-2")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--per-host", type=int, default=2, help="maks. równoległych zapytań na host")
    args = ap.parse_args()

    with open(args.catalog, encoding="utf-8") as f:
        catalog = json.load(f)
    if args.type:
        catalog = [e for e in catalog if e["type"] in args.type]
    if args.level:
        catalog = [e for e in catalog if e.get("level") == args.level]
    if args.ids:
        wanted = set(args.ids.split(","))
        catalog = [e for e in catalog if e["id"] in wanted]

    limiter = HostLimiter(args.per_host)
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(validate, e, args.timeout, limiter): e for e in catalog}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            r = fut.result()
            results.append(r)
            print(f"[{i}/{len(catalog)}] {r['status']:<18} {r['id']:<9} {r['name'][:60]}",
                  file=sys.stderr, flush=True)

    order = {e["id"]: n for n, e in enumerate(catalog)}
    results.sort(key=lambda r: order[r["id"]])

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "walidacja.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out_dir, "walidacja.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    by_type = collections.defaultdict(collections.Counter)
    for r in results:
        by_type[r["type"]][r["status"]] += 1
    for stype, counter in sorted(by_type.items()):
        print(f"{stype}: " + ", ".join(f"{k}={v}" for k, v in counter.most_common()))
    http_entries = [r for r in results if r["https_ok"] is not None]
    if http_entries:
        print(f"http:// w katalogu: {len(http_entries)}, działa po https: "
              f"{sum(1 for r in http_entries if r['https_ok'])}")


if __name__ == "__main__":
    main()
