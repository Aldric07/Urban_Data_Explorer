# Urban Data Explorer

Plateforme d'analyse du marché immobilier parisien — 20 arrondissements, 13 sources de données, pipeline Bronze → Silver → Gold avec batch nightly et streaming micro-batch.

## Architecture

```
Urban Data Explorer
├── ingestion/          # Collecte des 13 sources (Bronze)
├── pipeline/           # Transformations Bronze→Silver→Gold
│   ├── batch_processor.py        # Batch nightly DVF (APScheduler 02h00)
│   └── streaming_microbatch.py   # Micro-batch qualité air (30s)
├── db/                 # Schémas SQLAlchemy + client Mongo
├── api/                # Backend FastAPI (DuckDB + PostgreSQL + MongoDB)
├── dashboard/          # Frontend HTML + MapLibre GL JS
├── tests/              # Tests unitaires + tests de charge (Locust)
└── docs/               # Documentation architecture
```

```
data/
├── bronze/   # Données brutes (JSON, CSV originaux) — conservées dans git*
├── silver/   # Nettoyées + géocodées (Parquet) — générées, ignorées git
└── gold/     # Agrégats par arrondissement (Parquet) — générés, ignorés git
```

> \* Les fichiers lourds (DVF `.csv.gz`, revenus ZIP) sont exclus via `.gitignore`.

## Stack technique

| Couche | Technologie |
|---|---|
| Langage | Python 3.9 |
| Analytique | DuckDB, Parquet, pandas |
| Base relationnelle | PostgreSQL 16 + PostGIS |
| Base NoSQL | MongoDB 7 |
| API | FastAPI + uvicorn |
| Scheduler | APScheduler |
| Frontend | HTML + MapLibre GL JS |
| Infra | Docker Compose |
| Tests | pytest + Locust |

## Sources de données (13)

| Source | Indicateur | Format |
|---|---|---|
| DVF (data.gouv) | Prix immobiliers | CSV annuels |
| RPLS (data.gouv) | Logements sociaux | CSV |
| INSEE Filosofi | Revenus par IRIS | CSV |
| IDFM | Transports (métro/bus) | API GTFS |
| data.education.gouv | Écoles et lycées | API REST |
| FINESS | Santé (hôpitaux, médecins) | CSV |
| Overpass (OSM) | Parcs, commerces | API REST |
| AIRPARIF | Qualité de l'air | open data |
| SSMSI | Criminalité | CSV data.gouv |
| DRIHL | Loyers de référence | CSV |
| geo.api.gouv.fr | Contours arrondissements | GeoJSON |
| Paris Open Data | Circulation | API REST |
| BRUITPARIF | Bruit urbain | open data |

## Lancement rapide

```bash
# 1. Dépendances
pip install -r requirements.txt
# ou
make install

# 2. Ingestion Bronze
make ingest

# 3. Transformation Silver → Gold
make pipeline

# 4. Vérification du Data Lake
make check

# 5. Bases de données
make db-up       # démarre PostgreSQL (port 5433) + MongoDB (port 27017)
make load-db     # charge Gold → PostgreSQL, Bronze → MongoDB

# 6. API + Dashboard (via Docker)
docker compose up -d

# 7. Dashboard statique (hors Docker)
open dashboard/index.html
```

**Tout en une commande :**

```bash
make all-db   # install + ingest + pipeline + load-db + tests
```

## Services et ports

| Service | URL | Accès |
|---|---|---|
| API FastAPI | http://localhost:8000 | `Authorization: urban-explorer-dev-key` |
| Dashboard | http://localhost:3000 | — |
| Adminer (PostgreSQL) | http://localhost:8080 | user: `urban` / pwd: `urban_dev_pwd` |
| mongo-express | http://localhost:8081 | user: `urban-admin` / pwd: `urban_dev_pwd` |

## Commandes Make

```bash
make install          # Installe les dépendances Python
make ingest           # Télécharge toutes les sources (Bronze)
make pipeline         # Transforme Bronze → Silver → Gold
make stream           # Micro-batch streaming (démo 20 batchs)
make stream-continuous # Streaming continu (intervalle 30s)
make check            # Vérifie l'état du Data Lake
make test             # Lance pytest
make test-coverage    # pytest avec rapport de couverture
make api              # Démarre l'API FastAPI (port 8000)
make docker-up        # Lance tous les services Docker
make db-up            # Lance PostgreSQL + MongoDB uniquement
make db-ui            # Lance DB + Adminer + mongo-express
make load-postgres    # Charge Gold → PostgreSQL+PostGIS
make load-mongo       # Charge Bronze + catalogue → MongoDB
make load-db          # Charge les deux bases
make all              # Pipeline complet (sans DB)
make all-db           # Pipeline complet + chargement des DB
make clean            # Supprime Silver et Gold
```

## Architecture batch / streaming

- **Batch nightly** : `pipeline/batch_processor.py` — traitement DVF déclenché à 02h00 via APScheduler, rapport JSON sauvegardé dans `data/gold/batch_reports/`
- **Streaming micro-batch** : `pipeline/streaming_microbatch.py` — ingestion qualité air toutes les 30s avec fallback simulation, événements stockés dans MongoDB collection `stream_events`
- **Endpoints dédiés** : `/batch/status` et `/stream/air-quality` dans l'API

## Tests

```bash
make test            # Tests unitaires pipeline + API
make test-coverage   # Avec couverture de code
# Tests de charge Locust : tests/locustfile.py
```

## Documentation

| Fichier | Contenu |
|---|---|
| [docs/databases.md](docs/databases.md) | Schéma PG + Mongo, justification des choix |
| [docs/batch_streaming.md](docs/batch_streaming.md) | Architecture batch/streaming |
| [docs/data_catalog.md](docs/data_catalog.md) | Catalogue des 13 sources |
| [docs/architecture.md](docs/architecture.md) | Vue d'ensemble technique |
| [docs/rapport_pipeline.md](docs/rapport_pipeline.md) | Rapport pipeline |
