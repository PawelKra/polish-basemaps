# Polish Basemaps

Wtyczka RustGIS z zakładką polskich usług mapowych: ortofotomapa i mapy GUGiK, działki i budynki z ewidencji, plany miejscowe, granice, osnowy, Bank Danych o Lasach, formy ochrony przyrody, geologia PIG, mapy historyczne i zabytki.

Podkłady zastępują się nawzajem, a nakładki dokładają się na wierzch. Ponowne wybranie nakładki ją usuwa. Warstwy są zapisywane w projekcie razem z atrybucją.

## Zakładka

**Polish Basemaps**, na końcu paska zakładek:

- **Podkłady**: Ortofotomapa, Ortofotomapa HD, Mapa topograficzna, BDOT10k, **Mapy tematyczne ▾** (2)
- **Działki i planowanie**: Działki, Budynki, Działki z widoku, Uzbrojenie terenu, Plany miejscowe, Studium, Adresy, Ceny nieruchomości
- **Granice**: Granice administracyjne, Obręby ewidencyjne, Nazwy geograficzne, **Siatki i skorowidze ▾** (4), **Osnowy ▾** (5)
- **Przyroda**: **Lasy (BDL) ▾** (6), Zakazy wstępu do lasu, Zagrożenie pożarowe, **Ochrona przyrody ▾** (3), Zagrożenie powodziowe
- **Geologia**: Osuwiska, Podtopienia, **Geologia ▾** (6)
- **Historia**: **Mapy historyczne ▾** (8), **Zabytki ▾** (4)
- **Inne**: Zdrowie, Edukacja, Ludność (siatka 1 km)
- **Zarządzanie**: Usuń podkłady, Usuń nakładki, Bieżące

Komendy działają też z wyszukiwarki komend i z wiersza poleceń:

```sh
rustgis-cli run --plugin polish-basemaps-0.1.0.rgplugin \
  --cmd 'plugin:polish-basemaps/orto' \
  --cmd 'plugin:polish-basemaps/kieg-dzialki' \
  --cmd 'share.exportMap={"path":"mapa.png"}'
```

### Działki z widoku

Komenda bierze środek mapy, pyta usługę ULDK GUGiK o kod TERYT powiatu i dodaje warstwy działek i budynków z powiatowej usługi WFS EGiB, tylko dla widocznego obszaru. Działa w skali 1:25 000 i większej.

Zapytanie GetFeature składa sama wtyczka, z prostokątem widoku i limitem 10 000 obiektów na warstwę. Wbudowane `service.add` pobrałoby z WFS całą warstwę powiatu, do 50 000 obiektów.

RustGIS wczytuje WFS tylko w GeoJSON. Według stanu z października 2026 tak udostępnia dane 163 z 380 powiatów. Dla pozostałych komenda odsyła do nakładki „Działki” (KIEG).

## Ograniczenia

- RustGIS rysuje kafle tylko w Web Mercatorze (EPSG:3857). Usługi WMS są dodawane szablonem GetMap w 3857. Część serwerów GUGiK oddaje 3857, choć go nie ogłasza. Usługi, które przyjmują wyłącznie EPSG:2180, nie są dostępne: cieniowanie, hipsometria, mapa sozologiczna, LPIS i WMTS GUGiK poza ortofotomapą.
- KIEG pobiera kafle z serwerów powiatowych: odpowiada wolno (kilka sekund na kafel) i czasem zwraca błąd. Brakujący kafel doładuje się przy przesunięciu mapy.
- Warstwy ewidencyjne mają progi skali: działki od zoomu 16, budynki od 17, plany miejscowe od 14, ceny nieruchomości od 15. Te warstwy pobierają obrazy 512 px na kafel, bo serwery liczą próg skali z rozmiaru obrazu, a RustGIS na ekranach Retina pobiera kafle o jeden zoom niżej.
- BDOT10k to mapa topograficzna 1:10 000 PIG-PIB z danych BDOT10k, pobierana przez ArcGIS REST `export` (około 0,5 s na kafel), widoczna od zoomu 14. Kompozycja BDOT10k w WMS GUGiK renderuje kafel 40–60 s i RustGIS go nie doczekuje.

## Źródła i warunki

Dane pochodzą od ich wydawców i podlegają ich warunkom: GUGiK, GDOŚ, PIG-PIB, NID, PGW Wody Polskie, GUS, Bank Danych o Lasach (BULiGL, Lasy Państwowe) oraz pastmaps IH PAN. Każda warstwa ma atrybucję wyświetlaną w rogu mapy i w eksportach. Usługi są przeznaczone do lekkiego, interaktywnego użytku, nie do masowego pobierania.

Lista powiatowych usług WFS pochodzi z Ewidencji zbiorów i usług danych przestrzennych GUGiK (EZiUDP).

## Uprawnienia

`edit` i `network`: dodawanie warstw kafelkowych i warstw WFS, zapytanie do ULDK.

## Budowanie

```sh
python generate.py && cargo fmt
cargo test
cargo build --release --target wasm32-unknown-unknown
mkdir -p pkg && cp plugin.json pkg/ && cp target/wasm32-unknown-unknown/release/polish_basemaps.wasm pkg/plugin.wasm
(cd pkg && zip -X ../polish-basemaps-0.1.0.rgplugin plugin.json plugin.wasm)
```

`plugin.json`, `src/catalog.rs` i `src/egib.rs` generuje `generate.py` z jednej tabeli. Nie edytuj ich ręcznie.

Narzędzia w `tools/`:

- `check_tiles.py` pobiera kafel z każdego szablonu katalogu i sprawdza, czy ma treść.
- `build_egib.py` odświeża `data/egib.json` z eksportu EZiUDP i sprawdza każdy WFS w RustGIS.
- `validate_capabilities.py`, `probe_3857.py` i `rustgis_compat.py` sprawdzają nowe usługi przed dodaniem ich do katalogu.
