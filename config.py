"""
config.py — Configuration centralisée Urban Data Explorer
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DATA_DIR   = ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR   = DATA_DIR / "gold"

for d in [BRONZE_DIR, SILVER_DIR, GOLD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ARRONDISSEMENTS = list(range(1, 21))

# ── DVF — seules 2021-2025 disponibles dans latest ──────────────────────────
DVF_BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/75.csv.gz"
DVF_YEARS    = [2021, 2022, 2023, 2024]

# ── Contours arrondissements ─────────────────────────────────────────────────
GEO_ARRONDISSEMENTS_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "arrondissements/exports/geojson?lang=fr"
)

# ── RPLS logements sociaux ───────────────────────────────────────────────────
# Nouveau dataset data.gouv (vérifié mai 2025)
RPLS_DATASET_ID = "donnees-detaillees-au-logement-du-repertoire-des-logements-locatifs-des-bailleurs-sociaux-rpls"
RPLS_API_URL    = f"https://www.data.gouv.fr/api/1/datasets/{RPLS_DATASET_ID}/"

# ── Criminalité — nouveau dataset SSMSI ─────────────────────────────────────
CRIME_DATASET_ID = "bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales"
CRIME_API_URL    = f"https://www.data.gouv.fr/api/1/datasets/{CRIME_DATASET_ID}/"

# ── Loyers — Paris Open Data (source principale) ────────────────────────────
LOYERS_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "logement-encadrement-des-loyers/exports/csv"
    "?lang=fr&delimiter=%3B&timezone=Europe%2FParis&use_labels=true&epsg=4326"
)

# ── Revenus INSEE Filosofi ───────────────────────────────────────────────────
FILOSOFI_URL = (
    "https://www.insee.fr/fr/statistiques/fichier/7233950/"
    "indic-struct-distrib-revenu-2021-COMMUNES.zip"
)

# ── Transports IDFM ──────────────────────────────────────────────────────────
IDFM_STOPS_URL = (
    "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/"
    "emplacement-des-gares-idf/exports/json?lang=fr&limit=5000"
)

# ── Éducation ────────────────────────────────────────────────────────────────
EDUCATION_URL = (
    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/"
    "fr-en-annuaire-education/exports/json"
    "?lang=fr&refine=code_departement%3A075&limit=5000"
)

# ── Overpass OSM ─────────────────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ── API ──────────────────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_KEY  = os.getenv("API_KEY", "urban-explorer-dev-key")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Bases de données (BC1) ───────────────────────────────────────────────────
# Hors Docker : localhost. Dans Docker : surchargé par docker-compose.yml.
POSTGRES_URI = os.getenv(
    "POSTGRES_URI",
    "postgresql+psycopg2://urban:urban_dev_pwd@localhost:5433/urban_data",
)
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://urban:urban_dev_pwd@localhost:27017/urban_data?authSource=admin",
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "urban_data")
