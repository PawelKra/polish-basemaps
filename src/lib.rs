//! Polish Basemaps: zakładka z polskimi usługami mapowymi.
//!
//! Każda pozycja katalogu to komenda. Wybranie podkładu dodaje go przez `map.addTiles`
//! (uprawnienie `network`) i zastępuje dotychczasowy podkład; `{"add": true}` kładzie go
//! na wierzch. Nakładki trafiają nad podkład, a ponowne wybranie nakładki ją usuwa.
//!
//! „Działki z widoku” ustala powiat w środku mapy przez ULDK GUGiK i dodaje działki
//! i budynki z powiatowej usługi WFS EGiB dla widocznego obszaru (`layer.addUrl`).
//!
//! Katalog (`catalog.rs`), tabela powiatów (`egib.rs`) i komendy w `plugin.json`
//! są generowane przez `generate.py`.

use rustgis_plugin::{Value, host, json};

mod catalog;
mod egib;

pub use catalog::CATALOG;
pub use egib::POWIATY;

/// Podkład albo nakładka z katalogu.
#[derive(Clone, Copy, Debug)]
pub struct Entry {
    /// Id komendy, zapisywane też przy warstwie kafelkowej, żeby ją potem rozpoznać.
    pub id: &'static str,
    pub name: &'static str,
    /// Szablon kafla XYZ albo GetMap WMS z `{bbox-epsg-3857}`.
    pub url: &'static str,
    pub attribution: &'static str,
    pub min_zoom: u8,
    pub max_zoom: u8,
    /// Przezroczysta warstwa kładziona nad podkładem.
    pub overlay: bool,
}

/// Powiatowa usługa WFS EGiB.
#[derive(Clone, Copy, Debug)]
pub struct Powiat {
    pub teryt: &'static str,
    pub obszar: &'static str,
    pub url: &'static str,
    /// Nazwy warstw; puste, gdy usługa nie oddaje GeoJSON i RustGIS jej nie wczyta.
    pub dzialki: &'static str,
    pub budynki: &'static str,
    /// Zapytania GetFeature w GeoJSON (bez BBOX), do których doklejamy zasięg widoku.
    pub dzialki_getfeature: &'static str,
    pub budynki_getfeature: &'static str,
}

/// Największy mianownik skali, przy którym wczytujemy działki z WFS.
const MAX_SCALE: f64 = 25_000.0;

/// Najwięcej obiektów jednej warstwy w jednym zapytaniu do serwera powiatowego.
const MAX_FEATURES: u32 = 10_000;

fn handle(req: rustgis_plugin::Request) -> Result<Value, String> {
    if let Some(e) = CATALOG.iter().find(|e| e.id == req.id) {
        return choose(e, req.bool("add").unwrap_or(false));
    }
    match req.id.as_str() {
        "dzialki-z-widoku" => dzialki_z_widoku(),
        "clear" => clear(false),
        "clear-overlays" => clear(true),
        "current" => current(),
        other => Err(format!("Polish Basemaps nie ma komendy '{other}'")),
    }
}

rustgis_plugin::export!(handle);

/// Warstwy kafelkowe mapy, od góry: `[{"index", "name", "id", "overlay", …}]`.
fn tile_layers() -> Result<Vec<Value>, String> {
    host::run("map.tiles", json!({}))?
        .as_array()
        .cloned()
        .ok_or_else(|| "map.tiles zwróciło nieoczekiwaną odpowiedź".to_string())
}

/// Parametry `map.addTiles` dla pozycji katalogu.
pub fn add_params(e: &Entry, replace: bool) -> Value {
    json!({
        "url": e.url, "kind": "raster", "name": e.name, "attribution": e.attribution,
        "minZoom": e.min_zoom, "maxZoom": e.max_zoom, "tileSize": 256,
        "overlay": e.overlay, "id": e.id, "replace": replace,
    })
}

fn choose(e: &Entry, add: bool) -> Result<Value, String> {
    // Nakładka, która już jest na mapie, zostaje usunięta.
    if e.overlay && tile_layers()?.iter().any(|t| t["id"] == e.id) {
        host::run("map.removeTiles", json!({"id": e.id}))?;
        host::notify(&format!("Usunięto: {}", e.name));
        return Ok(json!({"removed": e.name}));
    }
    let out = host::run("map.addTiles", add_params(e, !e.overlay && !add))?;
    host::notify(&format!(
        "{} {}",
        if e.overlay { "Nakładka:" } else { "Podkład:" },
        e.name
    ));
    Ok(out)
}

/// Usuwa podkłady (albo nakładki) od dołu, żeby indeksy pozostały ważne.
fn clear(overlays: bool) -> Result<Value, String> {
    let mut removed = Vec::new();
    for t in tile_layers()?.iter().rev() {
        if t["overlay"].as_bool().unwrap_or(false) == overlays {
            host::run("map.removeTiles", json!({"index": t["index"]}))?;
            removed.push(t["name"].clone());
        }
    }
    let what = if overlays { "nakładek" } else { "podkładów" };
    host::notify(&if removed.is_empty() {
        format!("Brak {what} do usunięcia")
    } else {
        format!("Usunięto {what}: {}", removed.len())
    });
    Ok(json!({"removed": removed}))
}

fn current() -> Result<Value, String> {
    let layers = tile_layers()?;
    let names: Vec<&str> = layers.iter().filter_map(|t| t["name"].as_str()).collect();
    host::notify(&if names.is_empty() {
        "Brak warstw kafelkowych: widać wbudowany podkład".to_string()
    } else {
        names.join(" nad ")
    });
    Ok(Value::Array(layers))
}

/// Adres ULDK zwracający TERYT i nazwę powiatu dla punktu w WGS84.
pub fn uldk_url(lon: f64, lat: f64) -> String {
    format!(
        "https://uldk.gugik.gov.pl/?request=GetCountyByXY&xy={lon:.6},{lat:.6},4326&result=teryt,county"
    )
}

/// Odczytuje odpowiedź ULDK: pierwsza linia to status (`0` = sukces), druga `teryt|nazwa`.
pub fn parse_uldk(text: &str) -> Result<(String, String), String> {
    let mut lines = text.lines().map(str::trim).filter(|l| !l.is_empty());
    let status = lines.next().unwrap_or("");
    if status != "0" {
        return Err(format!("ULDK nie znalazło powiatu: {}", text.trim()));
    }
    let row = lines.next().ok_or("ULDK zwróciło pustą odpowiedź")?;
    let (teryt, name) = row.split_once('|').unwrap_or((row, ""));
    if teryt.len() != 4 || !teryt.chars().all(|c| c.is_ascii_digit()) {
        return Err(format!("ULDK zwróciło nieoczekiwany TERYT: {row}"));
    }
    Ok((teryt.to_string(), name.to_string()))
}

/// Prostokąt `[zachód, południe, wschód, północ]` w stopniach wokół środka widoku.
///
/// `host.view` podaje tylko środek i skalę, więc zasięg liczymy dla typowego okna mapy
/// (1600 × 1000 px po 0,28 mm). Przy 1:25 000 to około 11 × 7 km.
pub fn view_bbox(lon: f64, lat: f64, scale: f64) -> [f64; 4] {
    let half_w = scale * 0.000_28 * 800.0;
    let half_h = scale * 0.000_28 * 500.0;
    let dlon = half_w / (111_320.0 * lat.to_radians().cos());
    let dlat = half_h / 110_540.0;
    [lon - dlon, lat - dlat, lon + dlon, lat + dlat]
}

/// Zapytanie GetFeature z `[zachód, południe, wschód, północ]` i limitem obiektów.
///
/// Szablon pochodzi z RustGIS (`service.layers`) i ma `SRSNAME=EPSG:4326`. WFS 1.1 i 2.0
/// czytają BBOX w EPSG:4326 jako szerokość, długość, więc podajemy go z nazwą układu w postaci
/// URN, która tę kolejność wymusza; WFS 1.0 bierze długość, szerokość.
pub fn getfeature_url(template: &str, bbox: [f64; 4], limit: u32) -> String {
    let (base, query) = template.split_once('?').unwrap_or((template, ""));
    let mut version = "2.0.0";
    let mut params: Vec<&str> = Vec::new();
    for p in query.split('&').filter(|p| !p.is_empty()) {
        let key = p.split('=').next().unwrap_or("").to_ascii_uppercase();
        if key == "VERSION" {
            version = p.split_once('=').map_or(version, |(_, v)| v);
        }
        if !matches!(key.as_str(), "COUNT" | "MAXFEATURES" | "BBOX") {
            params.push(p);
        }
    }
    let [w, s, e, n] = bbox;
    let (limit_key, bbox_param) = match version {
        "1.0.0" => ("MAXFEATURES", format!("{w:.6},{s:.6},{e:.6},{n:.6}")),
        "1.1.0" => (
            "MAXFEATURES",
            format!("{s:.6},{w:.6},{n:.6},{e:.6},urn:ogc:def:crs:EPSG::4326"),
        ),
        _ => (
            "COUNT",
            format!("{s:.6},{w:.6},{n:.6},{e:.6},urn:ogc:def:crs:EPSG::4326"),
        ),
    };
    format!(
        "{base}?{}&{limit_key}={limit}&BBOX={bbox_param}",
        params.join("&")
    )
}

fn dzialki_z_widoku() -> Result<Value, String> {
    let view = host::view()?;
    let scale = view["scale"].as_f64().unwrap_or(f64::INFINITY);
    if scale > MAX_SCALE {
        return Err(format!(
            "Przybliż mapę do skali 1:{} lub większej (teraz 1:{:.0}), żeby wczytać działki z WFS.",
            MAX_SCALE as u32, scale
        ));
    }
    let (lon, lat) = match view["center"].as_array().map(Vec::as_slice) {
        Some([lon, lat]) => (lon.as_f64().unwrap_or(0.0), lat.as_f64().unwrap_or(0.0)),
        _ => return Err("host.view nie podał środka mapy".to_string()),
    };
    let answer = host::call("host.fetch", json!({"url": uldk_url(lon, lat)}))?;
    if answer["pending"].as_bool() == Some(true) {
        // Aplikacja webowa: RustGIS uruchomi komendę ponownie, gdy odpowiedź dotrze.
        return Ok(answer);
    }
    let (teryt, nazwa) = parse_uldk(answer["text"].as_str().unwrap_or(""))?;
    let p = POWIATY
        .iter()
        .find(|p| p.teryt == teryt)
        .ok_or_else(|| format!("Brak usługi WFS EGiB w rejestrze GUGiK dla {nazwa} ({teryt})."))?;
    if p.dzialki.is_empty() {
        return Err(format!(
            "WFS EGiB dla {} ({teryt}) nie oddaje GeoJSON, więc RustGIS go nie wczyta. Użyj nakładki „Działki” (KIEG).",
            p.obszar
        ));
    }
    // service.add pobiera z WFS całą warstwę (do 50 000 obiektów), bez zasięgu widoku.
    // Składamy więc GetFeature sami: z BBOX widoku i limitem, żeby nie pytać o cały powiat.
    let bbox = view_bbox(lon, lat, scale);
    let mut added = Vec::new();
    for (template, label) in [
        (p.dzialki_getfeature, "Działki"),
        (p.budynki_getfeature, "Budynki"),
    ] {
        if template.is_empty() {
            continue;
        }
        let name = format!("{label} – {}", p.obszar);
        let url = getfeature_url(template, bbox, MAX_FEATURES);
        host::run(
            "layer.addUrl",
            json!({"url": url, "name": name, "zoom": false, "service": true}),
        )?;
        added.push(name);
    }
    host::notify(&format!("Wczytano z WFS: {}", added.join(", ")));
    Ok(json!({"teryt": teryt, "added": added}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use rustgis_plugin::serde_json;

    #[test]
    fn catalog_and_manifest_agree() {
        let manifest: Value = serde_json::from_str(include_str!("../plugin.json")).unwrap();
        let commands: Vec<&str> = manifest["commands"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|c| c["id"].as_str())
            .collect();
        for e in CATALOG {
            assert!(commands.contains(&e.id), "{} nie ma komendy", e.id);
            assert!(e.url.starts_with("https://"), "{}: {}", e.id, e.url);
            assert!(
                e.url.contains("{bbox-epsg-3857}")
                    || (e.url.contains("{z}") && e.url.contains("{x}") && e.url.contains("{y}")),
                "{}: brak szablonu kafla",
                e.id
            );
            assert!(!e.attribution.is_empty(), "{} potrzebuje atrybucji", e.id);
            assert!(e.min_zoom <= e.max_zoom, "{}", e.id);
        }
        for c in commands {
            assert!(
                CATALOG.iter().any(|e| e.id == c)
                    || ["dzialki-z-widoku", "clear", "clear-overlays", "current"].contains(&c),
                "{c} nie jest obsługiwana"
            );
        }
        assert_eq!(manifest["permissions"], json!(["edit", "network"]));
    }

    #[test]
    fn builds_add_tiles_params() {
        let orto = CATALOG.iter().find(|e| e.id == "orto").unwrap();
        assert_eq!(add_params(orto, true)["replace"], true);
        let dzialki = CATALOG.iter().find(|e| e.id == "kieg-dzialki").unwrap();
        let p = add_params(dzialki, false);
        assert_eq!(p["overlay"], true);
        assert_eq!(p["minZoom"], 15);
    }

    #[test]
    fn parses_uldk_answers() {
        assert_eq!(
            parse_uldk("0\n1261|powiat Kraków\n").unwrap(),
            ("1261".into(), "powiat Kraków".into())
        );
        assert!(parse_uldk("-1 brak wyników").is_err());
        assert!(parse_uldk("0\n").is_err());
        assert!(uldk_url(19.94, 50.06).contains("xy=19.940000,50.060000,4326"));
    }

    #[test]
    fn builds_getfeature_urls() {
        let bbox = [19.1, 50.8, 19.2, 50.9];
        let v2 = getfeature_url(
            "https://x.pl/get?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=gmgml:dzialki&SRSNAME=EPSG:4326&COUNT=50000",
            bbox,
            100,
        );
        assert!(!v2.contains("50000"), "{v2}");
        assert!(
            v2.ends_with(
                "&COUNT=100&BBOX=50.800000,19.100000,50.900000,19.200000,urn:ogc:def:crs:EPSG::4326"
            ),
            "{v2}"
        );
        let v11 = getfeature_url(
            "https://x.pl/wfs?VERSION=1.1.0&TYPENAME=ewns:dzialki&MAXFEATURES=50000",
            bbox,
            100,
        );
        assert!(
            v11.contains("MAXFEATURES=100&BBOX=50.800000,19.100000"),
            "{v11}"
        );
        let v10 = getfeature_url(
            "https://x.pl/wfs?version=1.0.0&typename=dzialki&maxfeatures=50000",
            bbox,
            100,
        );
        assert!(
            v10.ends_with("&MAXFEATURES=100&BBOX=19.100000,50.800000,19.200000,50.900000"),
            "{v10}"
        );
        assert!(!v10.contains("maxfeatures=50000"), "{v10}");
    }

    #[test]
    fn view_bbox_is_small_at_max_scale() {
        let [w, s, e, n] = view_bbox(19.94, 50.06, MAX_SCALE);
        assert!(w < 19.94 && e > 19.94 && s < 50.06 && n > 50.06);
        // Przy 1:25 000 prostokąt ma kilka kilometrów, nie cały powiat.
        let km_x = (e - w) * 111.32 * 50.06_f64.to_radians().cos();
        let km_y = (n - s) * 110.54;
        assert!((10.0..12.0).contains(&km_x), "{km_x}");
        assert!((6.0..8.0).contains(&km_y), "{km_y}");
    }

    #[test]
    fn powiaty_are_unique_and_complete() {
        assert_eq!(POWIATY.len(), 380);
        assert!(
            POWIATY.windows(2).all(|w| w[0].teryt < w[1].teryt),
            "TERYT muszą być posortowane i unikalne"
        );
        // Budynki wczytujemy tylko razem z działkami.
        assert!(
            POWIATY
                .iter()
                .all(|p| !p.dzialki.is_empty() || p.budynki.is_empty())
        );
        for p in POWIATY.iter().filter(|p| !p.dzialki.is_empty()) {
            assert!(
                p.dzialki_getfeature.contains("GetFeature"),
                "{}: {}",
                p.teryt,
                p.dzialki_getfeature
            );
        }
    }
}
