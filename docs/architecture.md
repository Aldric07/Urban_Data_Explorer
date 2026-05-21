# Architecture technique — Urban Data Explorer

## Vue d'ensemble

```
SOURCES EXTERNES
data.gouv | INSEE | IDFM | OSM | AIRPARIF | Éducation
          │
          ▼
INGESTION  ingestion/run_all.py
• requests — HTTP avec retry et fallback
• Skip si déjà présent (idempotent)
          │
          ▼
BRONZE  data/bronze/
dvf/75_*.csv.gz | geo_arr.geojson | transports.json
revenus.csv | logements_sociaux.csv | criminalite.csv
loyers.csv | education.json | parcs.json | qualite_air.json
          │  pipeline/silver_*.py
          ▼
SILVER  data/silver/  [Parquet columnar]
dvf_all | transports | parcs | qualite_air
logements_sociaux | loyers | revenus | criminalite | geo_arr
geo-join spatial : coordonnées → arrondissement (GeoPandas)
          │  pipeline/gold_*.py
          ▼
GOLD  data/gold/  [Parquet]
agregats_arrondissements | indicateurs_custom | gold_final
stream/batch_*.parquet (micro-batch C2.2)
          │
     ┌────┴────┐
     ▼         ▼
API FastAPI   Streaming micro-batch
port 8000     toutes les N secondes
auth API key  → Parquet incrémental
     │
     ▼
DASHBOARD  dashboard/index.html
MapLibre GL JS — carte choroplèthe
Timeline | Comparaison | 4 indicateurs
```

## Compétences par composant

| Composant | Compétences RNCP |
|---|---|
| `ingestion/` | C2.3 |
| `data/bronze-silver-gold/` | C1.2, C1.3 |
| `pipeline/silver_*.py` | C2.3, C2.4 |
| `pipeline/gold_*.py` | C1.1, C2.3, C2.4 |
| `pipeline/streaming_microbatch.py` | C2.2 |
| `api/main.py` | C2.1 |
| `docker-compose.yml` + tests Locust | C1.4 |

## Choix technologiques

**Parquet** — Columnar, compression ~10x vs CSV, compatible DuckDB/pandas/Spark.

**DuckDB** — SQL in-process sur Parquet, zéro serveur, performances PostgreSQL.

**GeoPandas** — `sjoin()` pour rattacher coordonnées GPS → polygone arrondissement.

**FastAPI** — Async, auto-doc Swagger, validation Pydantic.

**MapLibre GL JS** — Fork open source Mapbox, WebGL, zéro clé API.

## Versioning données

```
Bronze légère (<10 Mo)  → git
Bronze lourde (DVF .gz) → .gitignore + make ingest
Silver + Gold           → .gitignore + make pipeline
```
