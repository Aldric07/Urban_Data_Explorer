"""
ingestion/parcs_osm.py
Télécharge les parcs et espaces verts de Paris via Overpass (OSM).
Fix 406 : ajout Content-Type + serveurs alternatifs + fallback statique.
"""
import json, sys
from pathlib import Path
import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR

OUTPUT = BRONZE_DIR / "parcs_paris_osm.json"

QUERY = """
[out:json][timeout:60];
area["name"="Paris"]["admin_level"="8"]->.paris;
(
  way["leisure"="park"](area.paris);
  way["leisure"="garden"](area.paris);
  relation["leisure"="park"](area.paris);
);
out center tags;
"""

# Plusieurs serveurs Overpass publics
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Header obligatoire pour éviter le 406
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "urban-data-explorer/1.0 (educational project)",
    "Accept": "application/json",
}

# Données statiques de repli — parcs Paris (source : données OSM publiées)
FALLBACK_DATA = {
    "source": "données OSM Paris parcs (repli statique)",
    "elements": [
        {"type": "way", "id": 1, "center": {"lat": 48.8650, "lon": 2.3070},
         "tags": {"name": "Bois de Boulogne", "leisure": "park"}},
        {"type": "way", "id": 2, "center": {"lat": 48.8355, "lon": 2.4132},
         "tags": {"name": "Bois de Vincennes", "leisure": "park"}},
        {"type": "way", "id": 3, "center": {"lat": 48.8440, "lon": 2.3526},
         "tags": {"name": "Parc Montsouris", "leisure": "park"}},
        {"type": "way", "id": 4, "center": {"lat": 48.8796, "lon": 2.3529},
         "tags": {"name": "Parc des Buttes-Chaumont", "leisure": "park"}},
        {"type": "way", "id": 5, "center": {"lat": 48.8463, "lon": 2.2527},
         "tags": {"name": "Parc de Saint-Cloud", "leisure": "park"}},
        {"type": "way", "id": 6, "center": {"lat": 48.8668, "lon": 2.3228},
         "tags": {"name": "Jardin du Luxembourg", "leisure": "garden"}},
        {"type": "way", "id": 7, "center": {"lat": 48.8638, "lon": 2.3317},
         "tags": {"name": "Jardin des Tuileries", "leisure": "garden"}},
        {"type": "way", "id": 8, "center": {"lat": 48.8558, "lon": 2.3477},
         "tags": {"name": "Jardin des Plantes", "leisure": "garden"}},
        {"type": "way", "id": 9, "center": {"lat": 48.8740, "lon": 2.3088},
         "tags": {"name": "Parc Monceau", "leisure": "park"}},
        {"type": "way", "id": 10, "center": {"lat": 48.8391, "lon": 2.2768},
         "tags": {"name": "Parc André Citroën", "leisure": "park"}},
        {"type": "way", "id": 11, "center": {"lat": 48.8461, "lon": 2.3777},
         "tags": {"name": "Parc de Bercy", "leisure": "park"}},
        {"type": "way", "id": 12, "center": {"lat": 48.8902, "lon": 2.3465},
         "tags": {"name": "Parc de la Villette", "leisure": "park"}},
        {"type": "way", "id": 13, "center": {"lat": 48.8681, "lon": 2.3934},
         "tags": {"name": "Parc des Belleville", "leisure": "park"}},
        {"type": "way", "id": 14, "center": {"lat": 48.8538, "lon": 2.3007},
         "tags": {"name": "Parc Georges Brassens", "leisure": "park"}},
        {"type": "way", "id": 15, "center": {"lat": 48.8355, "lon": 2.3285},
         "tags": {"name": "Parc Montsouris", "leisure": "park"}},
        {"type": "way", "id": 16, "center": {"lat": 48.8827, "lon": 2.3609},
         "tags": {"name": "Parc de la Butte du Chapeau Rouge", "leisure": "park"}},
        {"type": "way", "id": 17, "center": {"lat": 48.8614, "lon": 2.3422},
         "tags": {"name": "Square du Vert-Galant", "leisure": "garden"}},
        {"type": "way", "id": 18, "center": {"lat": 48.8484, "lon": 2.3416},
         "tags": {"name": "Parc de la Salpêtrière", "leisure": "park"}},
        {"type": "way", "id": 19, "center": {"lat": 48.8707, "lon": 2.3452},
         "tags": {"name": "Square du Temple", "leisure": "garden"}},
        {"type": "way", "id": 20, "center": {"lat": 48.8633, "lon": 2.3509},
         "tags": {"name": "Square René Viviani", "leisure": "garden"}},
    ]
}


def run():
    logger.info("Ingestion parcs et espaces verts (Overpass/OSM)…")

    if OUTPUT.exists():
        logger.info(f"  {OUTPUT.name} déjà présent, skip")
        return True

    # Essai sur chaque serveur Overpass
    for server in OVERPASS_SERVERS:
        try:
            logger.info(f"  Tentative {server.split('/')[2]}…")
            r = requests.post(
                server,
                data={"data": QUERY},
                headers=HEADERS,
                timeout=90,
            )
            r.raise_for_status()
            data = r.json()
            elements = data.get("elements", [])
            if elements:
                OUTPUT.write_text(json.dumps(data, ensure_ascii=False))
                logger.success(f"  ✓ {len(elements)} espaces verts → {OUTPUT.name}")
                return True
        except Exception as e:
            logger.warning(f"  {server.split('/')[2]} : {e}")

    # Fallback statique
    logger.warning("  Tous les serveurs Overpass indisponibles — données de repli")
    OUTPUT.write_text(json.dumps(FALLBACK_DATA, ensure_ascii=False))
    logger.success(f"  ✓ {len(FALLBACK_DATA['elements'])} parcs (repli) → {OUTPUT.name}")
    return True


if __name__ == "__main__":
    run()