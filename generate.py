"""Generuje plugin.json, src/catalog.rs i src/egib.rs wtyczki Polish Basemaps z jednej tabeli.

    python generate.py && cargo fmt

Zmieniaj tabelę (L) i układ zakładki tutaj, nigdy wygenerowanych plików.

RustGIS rysuje kafle tylko w Web Mercatorze (EPSG:3857). Usługi WMS dodajemy
szablonem GetMap z CRS=EPSG:3857 i BBOX={bbox-epsg-3857}; część serwerów GUGiK
oddaje 3857, choć go nie ogłasza (sprawdza to tools/probe_3857.py). Usługi
ogłaszające tylko EPSG:2180 i odrzucające 3857 nie trafiają do katalogu.
"""

import json
import pathlib
import urllib.parse

root = pathlib.Path(__file__).resolve().parent

GUGIK = "© Główny Urząd Geodezji i Kartografii"
GDOS = "© Generalna Dyrekcja Ochrony Środowiska"
PIG = "© Państwowy Instytut Geologiczny – PIB"
NID = "© Narodowy Instytut Dziedzictwa"
WODY = "© Państwowe Gospodarstwo Wodne Wody Polskie"
GUS = "© Główny Urząd Statystyczny"
IHPAN = "Mapy archiwalne: Instytut Historii PAN, pastmaps.cenagis.edu.pl"
BDL = "Źródło: Bank Danych o Lasach (BULiGL, Lasy Państwowe), bdl.lasy.gov.pl"

GEOPORTAL = "https://mapy.geoportal.gov.pl/wss"
INTEGRACJA = "https://integracja.gugik.gov.pl/cgi-bin"
CBDG = "https://cbdgmapa.pgi.gov.pl/arcgis/services"
PASTMAPS = "https://pastmaps.cenagis.edu.pl/geoserver/ihpan/wms"
NIDWMS = "https://usluga.zabytek.gov.pl/{}/service.svc/get"
GDOSWMS = "https://sdi.gdos.gov.pl/wms"

ORTO_WMTS = (GEOPORTAL + "/service/PZGIK/ORTO/WMTS/StandardResolution?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
             "&LAYER=ORTOFOTOMAPA&STYLE=default&TILEMATRIXSET=EPSG:3857&TILEMATRIX=EPSG:3857:{z}"
             "&TILEROW={y}&TILECOL={x}&FORMAT=image%2Fjpeg")


def wms(base, layers, fmt="image/png"):
    """Szablon kafla GetMap w EPSG:3857 dla map.addTiles."""
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query += [("SERVICE", "WMS"), ("VERSION", "1.3.0"), ("REQUEST", "GetMap"), ("LAYERS", layers),
              ("STYLES", ""), ("CRS", "EPSG:3857"), ("WIDTH", "256"), ("HEIGHT", "256"),
              ("FORMAT", fmt), ("TRANSPARENT", "TRUE")]
    q = urllib.parse.urlencode(query, safe=":/,")
    return urllib.parse.urlunsplit(parts._replace(query=q)) + "&BBOX={bbox-epsg-3857}"


# id, etykieta, podpowiedź, ikona, nakładka, adres, atrybucja, min zoom, max zoom
L = [
    # Podkłady
    ("orto", "Ortofotomapa", "Ortofotomapa standardowa GUGiK (kafle WMTS).", "raster_layer", False, ORTO_WMTS, GUGIK, 0, 19),
    ("orto-hd", "Ortofotomapa\nHD", "Ortofotomapa o wysokiej rozdzielczości GUGiK.", "raster_layer", False,
     wms(GEOPORTAL + "/service/PZGIK/ORTO/WMS/HighResolution", "Raster"), GUGIK, 0, 20),
    ("topo", "Mapa\ntopograficzna", "Rastrowa mapa topograficzna Polski GUGiK.", "relief", False,
     wms(GEOPORTAL + "/service/img/guest/TOPO/MapServer/WMSServer", "Raster"), GUGIK, 0, 18),
    ("ogolnogeograficzna", "Mapa ogólnogeograficzna", "Ogólnogeograficzna mapa Polski GUGiK.", "basemap", False,
     wms(GEOPORTAL + "/service/img/guest/Ogolnogeograficzna/MapServer/WMSServer", "Ogolnogeograficzna"), GUGIK, 0, 16),
    ("krajobrazowa", "Mapa krajobrazowa", "Krajobrazowa mapa Polski GUGiK.", "basemap", False,
     wms(GEOPORTAL + "/service/img/guest/Krajobrazowa/MapServer/WMSServer", "Krajobrazowa"), GUGIK, 0, 16),
    ("hydrograficzna", "Mapa hydrograficzna", "Mapa hydrograficzna Polski 1:50 000 GUGiK.", "basemap", False,
     wms(GEOPORTAL + "/service/img/guest/HYDRO/MapServer/WMSServer", "Raster"), GUGIK, 12, 16),

    # Działki i planowanie
    ("kieg-dzialki", "Działki", "Działki ewidencyjne z numerami (Krajowa Integracja Ewidencji Gruntów).", "line_layer", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaEwidencjiGruntow", "dzialki,numery_dzialek"), GUGIK, 15, 20),
    ("kieg-budynki", "Budynki", "Budynki z ewidencji gruntów i budynków (KIEG).", "line_layer", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaEwidencjiGruntow", "budynki"), GUGIK, 18, 20),
    ("kiut", "Uzbrojenie\nterenu", "Sieci uzbrojenia terenu (Krajowa Integracja Uzbrojenia Terenu).", "line_layer", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaUzbrojeniaTerenu",
         "przewod_wodociagowy,przewod_kanalizacyjny,przewod_elektroenergetyczny,przewod_gazowy,przewod_cieplowniczy,"
         "przewod_telekomunikacyjny,przewod_specjalny,przewod_niezidentyfikowany,przewod_urzadzenia"), GUGIK, 16, 20),
    ("kimp", "Plany\nmiejscowe", "Miejscowe plany zagospodarowania przestrzennego (KIMP).", "web_map", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaMiejscowychPlanowZagospodarowaniaPrzestrzennego",
         "raster,wektor-str,wektor-lzb,wektor-pow,wektor-lin,wektor-pkt,granice"), GUGIK, 15, 20),
    ("studium", "Studium", "Studia uwarunkowań i kierunków zagospodarowania przestrzennego gmin.", "web_map", True,
     wms(GEOPORTAL + "/ext/KrajowaIntegracjaStudiumKierunkowZagospodarowaniaPrzestrzennego", "studium"), GUGIK, 12, 20),
    ("adresy", "Adresy", "Punkty adresowe i ulice z Państwowego Rejestru Granic.", "label", True,
     wms(GEOPORTAL + "/ext/KrajowaIntegracjaNumeracjiAdresowej", "A08_Ulice_Linie,A07_Punkty_adresowe"), GUGIK, 15, 20),
    ("ceny", "Ceny\nnieruchomości", "Transakcje z rejestru cen nieruchomości: działki, budynki i lokale.", "stats", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaCenNieruchomosci", "dzialki,budynki,lokale"), GUGIK, 16, 20),

    # Granice i siatki
    ("prg", "Granice\nadministracyjne", "Granice państwa, województw, powiatów i gmin (PRG).", "line_layer", True,
     wms(GEOPORTAL + "/service/PZGIK/PRG/WMS/AdministrativeBoundaries",
         "A00_Granice_panstwa,A01_Granice_wojewodztw,A02_Granice_powiatow,A03_Granice_gmin"), GUGIK, 0, 20),
    ("obreby", "Obręby\newidencyjne", "Granice jednostek i obrębów ewidencyjnych (PRG).", "line_layer", True,
     wms(GEOPORTAL + "/service/PZGIK/PRG/WMS/AdministrativeBoundaries",
         "A05_Granice_jednostek_ewidencyjnych,A06_Granice_obrebow_ewidencyjnych"), GUGIK, 11, 20),
    ("prng", "Nazwy\ngeograficzne", "Urzędowe nazwy miejscowości i obiektów fizjograficznych (PRNG).", "label", True,
     wms(GEOPORTAL + "/service/PZGiK/PRNG/WMS/GeographicalNames",
         "O1_UrzedoweNazwyObiektowFizjograficznych,M1_UrzedoweNazwyMiejscowosci"), GUGIK, 0, 20),
    ("siatka-geo", "Siatka geograficzna", "Siatka stopniowa, minutowa i sekundowa.", "zoom_world", True,
     wms("https://wms02.epodgik.pl/cgi-bin/7/mapserv?map=/srv/webgis/siatka.map", "stopniowa,minutowa,sekundowa"), GUGIK, 0, 20),
    ("siatka-km", "Siatka kilometrowa", "Siatka kilometrowa układu 1992.", "zoom_world", True,
     wms("https://wms02.epodgik.pl/cgi-bin/7/mapserv?map=/srv/webgis/siatka92.map", "kilometrowa100,kilometrowa10,kilometrowa"), GUGIK, 0, 20),
    ("skorowidz-orto", "Skorowidz ortofotomap", "Arkusze ortofotomap z lat 2024–2026 i starszych.", "raster_layer", True,
     wms(GEOPORTAL + "/service/PZGIK/ORTO/WMS/SkorowidzeWgAktualnosci",
         "SkorowidzeOrtofotomapyStarsze,SkorowidzeOrtofotomapy2024,SkorowidzeOrtofotomapy2025,SkorowidzeOrtofotomapy2026"), GUGIK, 8, 20),
    ("skorowidz-zdjec", "Skorowidz zdjęć lotniczych", "Zdjęcia lotnicze z lat 2021–2026.", "raster_layer", True,
     wms(GEOPORTAL + "/service/PZGIK/ZDJ/WMS/SkorWgAktualnosci", "Zdjecia_lotnicze_2021-2025,Zdjecia_lotnicze_2026"), GUGIK, 8, 20),
    ("osnowa-pozioma", "Osnowa pozioma", "Podstawowa osnowa geodezyjna pozioma: punkty fundamentalne i bazowe.", "bookmark", True,
     wms(GEOPORTAL + "/service/PZGIK/PodstawowaOsnowaGeodezyjnaPozioma",
         "Fundamentalna_pozioma,Bazowa_pozioma,Fudnamentalna_pozioma_etykiety,Bazowa_pozioma_etykiety"), GUGIK, 0, 20),
    ("osnowa-wysokosciowa", "Osnowa wysokościowa", "Podstawowa osnowa geodezyjna wysokościowa.", "bookmark", True,
     wms(GEOPORTAL + "/service/PZGIK/PodstawowaOsnowaGeodezyjnaWysokosciowa",
         "Fundamentalna_wysokosciowa,Bazowa_wysokosciowa,Fudnamentalna_wysokosciowa_etykiety,Bazowa_wysokosciowa_etykiety"), GUGIK, 0, 20),
    ("osnowa-grawimetryczna", "Osnowa grawimetryczna", "Punkty osnowy grawimetrycznej.", "bookmark", True,
     wms(GEOPORTAL + "/service/PZGIK/OsnowaGrawimetryczna",
         "Fundamentalna_grawimetryczna,Bazowa_grawimetryczna,Fudnamentalna_grawimetryczna_etykiety,Bazowa_grawimetryczna_etykiety"), GUGIK, 0, 20),
    ("osnowa-magnetyczna", "Osnowa magnetyczna", "Punkty osnowy magnetycznej i izogony.", "bookmark", True,
     wms(GEOPORTAL + "/service/PZGIK/OsnowaMagnetyczna",
         "izogony,izogony_etykiety,Fundamentalna_magnetyczna,Bazowa_magnetyczna,Fudnamentalna_magnetyczna_etykiety,Bazowa_magnetyczna_etykiety"), GUGIK, 0, 20),
    ("osnowa-szczegolowa", "Osnowa szczegółowa", "Szczegółowe osnowy geodezyjne z powiatów (KISOG).", "bookmark", True,
     wms(INTEGRACJA + "/KrajowaIntegracjaSzczegolowychOsnowGeodezyjnych", "osnowa-XY,osnowa-H,osnowa-XYH"), GUGIK, 15, 20),

    # Przyroda
    ("parki-rezerwaty", "Parki i rezerwaty", "Parki narodowe, parki krajobrazowe i rezerwaty przyrody (GDOŚ).", "basemap", True,
     wms(GDOSWMS, "GDOS:ParkiKrajobrazowe,GDOS:ParkiNarodowe,GDOS:Rezerwaty"), GDOS, 0, 20),
    ("natura2000", "Natura 2000", "Obszary specjalnej ochrony ptaków i specjalne obszary ochrony siedlisk (GDOŚ).", "basemap", True,
     wms(GDOSWMS, "GDOS:ObszarySpecjalnejOchrony,GDOS:SpecjalneObszaryOchrony"), GDOS, 0, 20),
    ("ochrona-inne", "Pozostałe formy ochrony", "Obszary chronionego krajobrazu, zespoły przyrodniczo-krajobrazowe, użytki ekologiczne, stanowiska dokumentacyjne i pomniki przyrody (GDOŚ).", "basemap", True,
     wms(GDOSWMS, "GDOS:ObszaryChronionegoKrajobrazu,GDOS:ZespolyPrzyrodniczoKrajobrazowe,GDOS:UzytkiEkologiczne,"
         "GDOS:StanowiskaDokumentacyjne,GDOS:PomnikiPrzyrody"), GDOS, 0, 20),
    ("powodz", "Zagrożenie\npowodziowe", "Obszary szczególnego zagrożenia powodzią (1%) od strony rzek i morza.", "relief", True,
     wms("https://wody.isok.gov.pl/gpservices/KZGW/MZP20_ObszarySzczegolnegoZagrozeniaPowodzia/MapServer/WMSServer", "0,1"), WODY, 0, 20),

    # Geologia
    ("osuwiska", "Osuwiska", "Osuwiska i tereny zagrożone ruchami masowymi (SOPO, PIG-PIB).", "relief", True,
     wms(CBDG + "/geozagrozenia/sopo_obszary/MapServer/WMSServer", "0,13"), PIG, 0, 20),
    ("podtopienia", "Podtopienia", "Obszary podtopień (PIG-PIB).", "relief", True,
     wms(CBDG + "/hydrogeologia/podtopienia/MapServer/WMSServer", "0"), PIG, 0, 20),
    ("midas", "Złoża i tereny górnicze", "Udokumentowane złoża kopalin, obszary i tereny górnicze (MIDAS).", "relief", True,
     wms(CBDG + "/midas/MapServer/WMSServer", "3,4,5"), PIG, 0, 20),
    ("otwory", "Otwory wiertnicze", "Otwory wiertnicze z Centralnej Bazy Danych Geologicznych.", "relief", True,
     wms(CBDG + "/cbdg_otwory/MapServer/WMSServer", "0"), PIG, 0, 20),
    ("otwory-hydro", "Otwory hydrogeologiczne", "Otwory z Centralnej Bazy Danych Hydrogeologicznych.", "relief", True,
     wms(CBDG + "/hydrogeologia/cbdh_otwory/MapServer/WMSServer", "0"), PIG, 0, 20),
    ("smgp", "Szczegółowa mapa geologiczna", "Szczegółowa mapa geologiczna Polski 1:50 000 (PIG-PIB).", "relief", True,
     wms(CBDG + "/kartografia/smgp50k/MapServer/WMSServer", "0,1,2,3,4"), PIG, 0, 20),
    ("jaskinie", "Jaskinie", "Jaskinie Polski (PIG-PIB).", "relief", True,
     wms(CBDG + "/jaskinie/MapServer/WMSServer", "0"), PIG, 0, 20),
    ("monitoring-wod", "Monitoring wód podziemnych", "Punkty monitoringu wód podziemnych (PIG-PIB).", "relief", True,
     wms(CBDG + "/hydrogeologia/mwp/MapServer/WMSServer", "0"), PIG, 0, 20),

    # Historia i zabytki
    ("wig25k", "Mapa szczegółowa WIG 1:25 000", "Mapa szczegółowa Wojskowego Instytutu Geograficznego (1918–1939).", "history", False,
     wms(PASTMAPS, "wig25k_3857"), IHPAN, 0, 17),
    ("wig100k", "Mapa taktyczna WIG 1:100 000", "Mapa taktyczna Polski WIG (1918–1939).", "history", False,
     wms(PASTMAPS, "wig100k_3857"), IHPAN, 0, 15),
    ("wig300k", "Mapa operacyjna WIG 1:300 000", "Mapa operacyjna WIG (1918–1939).", "history", False,
     wms(PASTMAPS, "wig300k_3857"), IHPAN, 0, 13),
    ("messtischblatt", "Meßtischblätter 1:25 000", "Niemieckie mapy topograficzne 1:25 000 (1870–1945).", "history", False,
     wms(PASTMAPS, "m25k_3857"), IHPAN, 0, 17),
    ("kdr", "Karte des Deutschen Reiches 1:100 000", "Mapa Rzeszy Niemieckiej 1:100 000 (ok. 1900).", "history", False,
     wms(PASTMAPS, "kdr_3857"), IHPAN, 0, 15),
    ("kdwr", "Karte des westlichen Russlands 1:100 000", "Mapa zachodniej Rosji 1:100 000 (1914–1920).", "history", False,
     wms(PASTMAPS, "kdwr_3857"), IHPAN, 0, 15),
    ("kummersberg", "Mapa Galicji Kummersberga 1:115 000", "Administrativ-Karte Galizien und Lodomerien C. R. von Kummersberga.", "history", False,
     wms(PASTMAPS, "kummersberg_3857"), IHPAN, 0, 14),
    ("tkkp", "Topograficzna Karta Królestwa Polskiego", "Topograficzna Karta Królestwa Polskiego 1:126 000 (Mapa Kwatermistrzostwa).", "history", False,
     wms(PASTMAPS, "TKKP_126k_3857"), IHPAN, 0, 14),
    ("zabytki-nieruchome", "Rejestr zabytków nieruchomych", "Zabytki nieruchome wpisane do rejestru (NID).", "bookmark", True,
     wms(NIDWMS.format("INSPIRE_IMD"), "Immovable_Monuments"), NID, 0, 20),
    ("zabytki-archeologiczne", "Zabytki archeologiczne", "Rejestr zabytków archeologicznych (NID).", "bookmark", True,
     wms(NIDWMS.format("INSPIRE_AMD"), "Archaeological_Monuments"), NID, 0, 20),
    ("pomniki-historii", "Pomniki historii", "Pomniki historii (NID).", "bookmark", True,
     wms(NIDWMS.format("INSPIRE_MHD"), "Monuments_of_History"), NID, 0, 20),
    ("unesco", "Światowe dziedzictwo UNESCO", "Obiekty z Listy światowego dziedzictwa UNESCO w Polsce (NID).", "bookmark", True,
     wms(NIDWMS.format("INSPIRE_WHD"), "World_Heritage_Properties_List"), NID, 0, 20),

    # Inne
    ("zdrowie", "Zdrowie", "Szpitale, SOR, nocna pomoc lekarska i apteki.", "bookmark", True,
     wms(GEOPORTAL + "/ext/GUGIK/Zdrowie", "szpitale,sor,nocna_pomoc,apteki"), GUGIK, 0, 20),
    ("edukacja", "Edukacja", "Przedszkola, szkoły podstawowe, licea i inne placówki.", "bookmark", True,
     wms(GEOPORTAL + "/ext/GUGiK/Edukacja", "przedszkola,podstawowe,licea,inne"), GUGIK, 0, 20),
    ("ludnosc", "Ludność\n(siatka 1 km)", "Liczba ludności w siatce kilometrowej (GUS, NSP 2011).", "stats", True,
     wms("https://geo.stat.gov.pl/wss/wms_inspire/wms", "PdGridTotalPop"), GUS, 0, 20),
]


def bdl_wmts(service):
    """Kafle WMTS Banku Danych o Lasach w siatce GoogleMapsCompatible, podawane jako XYZ."""
    return (f"https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services/{service}/MapServer/WMTS/tile/1.0.0/"
            f"{service}/default/GoogleMapsCompatible/{{z}}/{{y}}/{{x}}.png")


BDL_WMS = "https://mapserver.bdl.lasy.gov.pl/ArcGIS/services/{}/MapServer/WMSServer"

# Bank Danych o Lasach. Nazwy warstw WMS pochodzą z GetCapabilities (nie z ArcGIS REST, numeracja się różni).
L += [
    ("bdl-podzial", "Oddziały\nleśne", "Nadleśnictwa, leśnictwa, oddziały i wydzielenia (BDL).", "line_layer", True,
     bdl_wmts("WMTS_BDL"), BDL, 6, 17),
    ("bdl-drzewostany", "Drzewostany", "Mapa drzewostanów (BDL).", "basemap", True,
     bdl_wmts("WMTS_BDL_mapa_drzewostanow"), BDL, 8, 17),
    ("bdl-siedliska", "Siedliska leśne", "Typy siedliskowe lasu (BDL).", "basemap", True,
     bdl_wmts("WMTS_BDL_mapa_siedlisk"), BDL, 8, 17),
    ("bdl-wlasnosc", "Własność lasów", "Lasy według kategorii własności (BDL).", "basemap", True,
     bdl_wmts("WMTS_BDL_kat_wlasnosci"), BDL, 14, 17),
    ("bdl-zakazy", "Zakazy wstępu\ndo lasu", "Okresowe zakazy wstępu do lasu na tle granic nadleśnictw (BDL).", "delete", True,
     wms(BDL_WMS.format("WMS_zakazy_wstepu_do_lasu"), "1,3"), BDL, 6, 20),
    ("bdl-pozary", "Zagrożenie\npożarowe", "Bieżący stopień zagrożenia pożarowego lasów (BDL).", "relief", True,
     wms(BDL_WMS.format("WMS_zagrozenie_pozarowe_w_lasach"), "0"), BDL, 5, 20),
    ("bdl-dojazdy", "Dojazdy pożarowe", "Drogi i punkty dojazdu pożarowego (BDL).", "line_layer", True,
     bdl_wmts("WMTS_BDL_dojazdy_pozarowe"), BDL, 8, 15),
    ("bdl-lowieckie", "Obwody łowieckie", "Granice obwodów łowieckich (BDL).", "line_layer", True,
     bdl_wmts("WMTS_BDL_Obwody_lowieckie"), BDL, 6, 13),
]

EXTRA = [
    {"id": "dzialki-z-widoku", "label": "Działki\nz widoku",
     "help": "Wczytuje działki i budynki z powiatowej usługi WFS EGiB dla widocznego obszaru (skala 1:25 000 lub większa). Powiat ustala usługa ULDK GUGiK.",
     "icon": "buffer"},
    {"id": "clear", "label": "Usuń\npodkłady", "help": "Usuwa podkłady wtyczki i wraca do wbudowanego podkładu. Nakładki zostają.", "icon": "delete"},
    {"id": "clear-overlays", "label": "Usuń\nnakładki", "help": "Usuwa wszystkie nakładki.", "icon": "clear_sel"},
    {"id": "current", "label": "Bieżące", "help": "Pokazuje na pasku stanu warstwy kafelkowe mapy.", "icon": "stats"},
]


def menu(label, icon, help, items):
    return {"menu": label, "icon": icon, "help": help, "items": items}


tab = {"label": "Polish Basemaps", "groups": [
    {"label": "Podkłady", "items": [
        "orto", "orto-hd", "topo",
        menu("Mapy\ntematyczne", "basemap", "Mapy tematyczne GUGiK.", ["ogolnogeograficzna", "krajobrazowa", "hydrograficzna"]),
    ]},
    {"label": "Działki i planowanie", "items": [
        "kieg-dzialki", "kieg-budynki", "dzialki-z-widoku", "kiut", "kimp", "studium", "adresy", "ceny",
    ]},
    {"label": "Granice", "items": [
        "prg", "obreby", "prng",
        menu("Siatki i\nskorowidze", "zoom_world", "Siatki kartograficzne i skorowidze.",
             ["siatka-geo", "siatka-km", "skorowidz-orto", "skorowidz-zdjec"]),
        menu("Osnowy", "bookmark", "Osnowy geodezyjne.",
             ["osnowa-pozioma", "osnowa-wysokosciowa", "osnowa-grawimetryczna", "osnowa-magnetyczna", "osnowa-szczegolowa"]),
    ]},
    {"label": "Przyroda", "items": [
        menu("Lasy\n(BDL)", "basemap", "Bank Danych o Lasach. Nakładki: wybierz ponownie, żeby usunąć.",
             ["bdl-podzial", "bdl-drzewostany", "bdl-siedliska", "bdl-wlasnosc", "bdl-dojazdy", "bdl-lowieckie"]),
        "bdl-zakazy", "bdl-pozary",
        menu("Ochrona\nprzyrody", "basemap", "Formy ochrony przyrody (GDOŚ).", ["parki-rezerwaty", "natura2000", "ochrona-inne"]),
        "powodz",
    ]},
    {"label": "Geologia", "items": [
        "osuwiska", "podtopienia",
        menu("Geologia", "relief", "Dane Państwowego Instytutu Geologicznego.",
             ["midas", "otwory", "otwory-hydro", "smgp", "jaskinie", "monitoring-wod"]),
    ]},
    {"label": "Historia", "items": [
        menu("Mapy\nhistoryczne", "history", "Mapy archiwalne z serwisu pastmaps IH PAN. Zastępują podkład.",
             ["wig25k", "wig100k", "wig300k", "messtischblatt", "kdr", "kdwr", "kummersberg", "tkkp"]),
        menu("Zabytki", "bookmark", "Rejestry Narodowego Instytutu Dziedzictwa.",
             ["zabytki-nieruchome", "zabytki-archeologiczne", "pomniki-historii", "unesco"]),
    ]},
    {"label": "Inne", "items": ["zdrowie", "edukacja", "ludnosc"]},
    {"label": "Zarządzanie", "items": ["clear", "clear-overlays", "current"]},
]}

ids = [row[0] for row in L] + [c["id"] for c in EXTRA]
assert len(ids) == len(set(ids)), "powtórzone id"
assert len(ids) <= 64, f"{len(ids)} komend, RustGIS przyjmuje najwyżej 64"
used = {i for g in tab["groups"] for it in g["items"] for i in (it["items"] if isinstance(it, dict) else [it])}
assert used == set(ids), (set(ids) - used, used - set(ids))

PARAMS = '{"add"?: bool (dodaje podkład na wierzch zamiast zastępować obecne)}'
commands = []
for (i, label, help, icon, overlay, url, att, minz, maxz) in L:
    c = {"id": i, "label": label,
         "help": help + (" Nakładka: wybierz ją ponownie, żeby ją usunąć." if overlay else ""), "icon": icon}
    if not overlay:
        c["params"] = PARAMS
    commands.append(c)
commands += EXTRA

manifest = {
    "id": "polish-basemaps", "name": "Polish Basemaps", "version": "0.1.0",
    "description": "Zakładka z polskimi usługami mapowymi: ortofotomapa i mapy GUGiK, działki i budynki z ewidencji, plany miejscowe, granice, osnowy, formy ochrony przyrody, geologia PIG, mapy historyczne i zabytki. Podkłady zastępują się nawzajem, nakładki dokładają się na wierzch.",
    "author": "Pawel Krapiec", "homepage": "",
    "license": "MIT", "entry": "plugin.wasm", "abi": 1, "minRustgisVersion": "0.4.0",
    "permissions": ["edit", "network"],
    "commands": commands, "tab": tab,
}
(root / "plugin.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rs(s):
    return json.dumps(s, ensure_ascii=False)


lines = ["//! Katalog: wszystkie podkłady i nakładki wtyczki. Wygenerowany przez `generate.py` razem",
         "//! z komendami w `plugin.json` z jednej tabeli (test sprawdza, że się zgadzają).", "",
         "use crate::Entry;", "", "pub const CATALOG: &[Entry] = &["]
for (i, label, help, icon, overlay, url, att, minz, maxz) in L:
    name = label.replace("\n", " ")
    lines.append(f"    Entry {{ id: {rs(i)}, name: {rs(name)}, url: {rs(url)}, attribution: {rs(att)}, "
                 f"min_zoom: {minz}, max_zoom: {maxz}, overlay: {'true' if overlay else 'false'} }},")
lines.append("];")
(root / "src" / "catalog.rs").write_text("\n".join(lines) + "\n", encoding="utf-8")

egib = json.loads((root / "data" / "egib.json").read_text(encoding="utf-8"))
lines = ["//! Powiatowe usługi WFS EGiB według TERYT. Wygenerowane przez `generate.py` z `data/egib.json`",
         "//! (tools/build_egib.py, źródło: EZiUDP GUGiK). Puste nazwy warstw: usługa nie oddaje GeoJSON.", "",
         "use crate::Powiat;", "", "pub const POWIATY: &[Powiat] = &["]
for p in egib:
    lines.append(f"    Powiat {{ teryt: {rs(p['teryt'])}, obszar: {rs(p['obszar'])}, url: {rs(p['url'])}, "
                 f"dzialki: {rs(p['dzialki'])}, budynki: {rs(p['budynki'])}, "
                 f"dzialki_getfeature: {rs(p['dzialki_getfeature'])}, budynki_getfeature: {rs(p['budynki_getfeature'])} }},")
lines.append("];")
(root / "src" / "egib.rs").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(len(L), "warstw,", len(commands), "komend,", sum(1 for p in egib if p["dzialki"]), "powiatów z WFS GeoJSON")
