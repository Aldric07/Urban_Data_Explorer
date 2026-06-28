# Urban Data Explorer

Plateforme d'analyse du marché immobilier et de la qualité de vie à Paris — 20 arrondissements, 13 sources open data, pipeline Bronze → Silver → Gold, batch nightly et streaming micro-batch.

**Certification RNCP40875 — Bloc 1 Architecture de données**
Compétences : C1.1 · C1.2 · C1.3 · C1.4 · C2.1 · C2.2 · C2.3 · C2.4

---

## Prérequis

- **Python 3.12** (ou 3.10+)
- **Docker + Docker Compose v2** (`docker compose` sans tiret)
- **Make**

---

## Lancement complet (recommandé)

```bash
# 1. Cloner et entrer dans le projet
cd Urban_Data_Explorer

# 2. Créer le venv et installer les dépendances
make install

# 3. Ingestion des 13 sources → Bronze
make ingest

# 4. Pipeline Bronze → Silver → Gold
make pipeline

# 5. Démarrer les services Docker (PostgreSQL + MongoDB + API + Dashboard)
docker compose up -d

# 6. Charger les données dans les bases
make load-db

# 7. Vérifier le Data Lake
make check
```

L'ensemble des services est maintenant disponible :

| Service | URL | Credentials |
|---|---|---|
| **API FastAPI** | http://localhost:8000 | Header : `Authorization: urban-explorer-dev-key` |
| **Dashboard** | http://localhost:3000 | — |
| **Swagger /docs** | http://localhost:8000/docs | — |
| **Adminer (PostgreSQL)** | http://localhost:8080 | Système: `PostgreSQL` · Serveur: `postgres` · User: `urban` · Pwd: `urban_dev_pwd` · Base: `urban_data` |
| **mongo-express (MongoDB)** | http://localhost:8081 | User: `urban-admin` · Pwd: `urban_dev_pwd` |

---

## Commandes Make

```bash
make install           # Crée venv/ et installe les dépendances
make ingest            # Télécharge les 13 sources → data/bronze/
make pipeline          # Transforme Bronze → Silver → Gold (Parquet)
make check             # Vérifie tailles et lignes de chaque couche
make load-postgres     # Charge Gold → PostgreSQL + PostGIS
make load-mongo        # Charge Bronze + catalogue → MongoDB
make load-db           # Charge PostgreSQL ET MongoDB
make stream            # Streaming micro-batch démo (20 batchs, 1s)
make stream-continuous # Streaming continu AIRPARIF (intervalle 30s)
make test              # Tests pytest
make test-coverage     # pytest avec couverture de code
make api               # Lance l'API FastAPI hors Docker (port 8000)
make clean             # Supprime data/silver/ et data/gold/
```

> **Note** : toutes les commandes `make` utilisent automatiquement `venv/bin/python3`. Pas besoin d'activer le venv manuellement.

---

## Commandes Docker

```bash
docker compose up -d              # Démarre les 6 services en arrière-plan
docker compose up -d --build api  # Rebuild l'image API puis démarre
docker compose ps                 # Statut des services
docker compose logs api -f        # Logs en temps réel de l'API
docker compose logs postgres -f   # Logs PostgreSQL
docker compose down               # Arrête et supprime les containers
```

Services disponibles après `docker compose up -d` :

| Service | Port | Rôle |
|---|---|---|
| `postgres` | 5433 (hôte) → 5432 (interne) | PostgreSQL 16 + PostGIS |
| `mongo` | 27017 | MongoDB 7 |
| `api` | 8000 | FastAPI REST |
| `dashboard` | 3000 | Frontend nginx |
| `adminer` | 8080 | UI web PostgreSQL |
| `mongo-express` | 8081 | UI web MongoDB |

---

## Credentials

### PostgreSQL (Adminer — http://localhost:8080)
| Champ | Valeur |
|---|---|
| Système | PostgreSQL |
| Serveur | `postgres` (depuis Docker) ou `localhost` (hors Docker) |
| Utilisateur | `urban` |
| Mot de passe | `urban_dev_pwd` |
| Base de données | `urban_data` |
| Port | `5432` (Docker interne) ou `5433` (hôte) |

### MongoDB (mongo-express — http://localhost:8081)
| Champ | Valeur |
|---|---|
| Utilisateur | `urban-admin` |
| Mot de passe | `urban_dev_pwd` |

### API Key
```
Authorization: urban-explorer-dev-key
```

---

## Architecture

```
Sources (13 APIs)
    │
    ▼
data/bronze/          ← JSON, CSV, GeoJSON bruts (idempotents)
    │  ingestion/run_all.py
    ▼
data/silver/          ← Parquet nettoyé + géo-join arrondissement
    │  pipeline/silver_*.py
    ▼
data/gold/            ← Parquet agrégés (prix_m2 × arrond × année)
    │
    ├──► PostgreSQL 16 + PostGIS   (load_postgres.py)
    ├──► MongoDB 7                  (load_mongo.py)
    └──► API FastAPI ──► Dashboard
```

```
Urban_Data_Explorer/
├── ingestion/          # 13 scripts d'ingestion Bronze
├── pipeline/           # Transformations Silver → Gold
│   ├── batch_processor.py        # Batch DVF nightly (APScheduler 02h00)
│   ├── streaming_microbatch.py   # Micro-batch qualité air (30s)
│   ├── load_postgres.py          # Chargement PostgreSQL
│   └── load_mongo.py             # Chargement MongoDB
├── db/                 # Schémas SQLAlchemy + client MongoDB
├── api/                # Backend FastAPI (11 endpoints)
├── dashboard/          # Frontend HTML + MapLibre GL JS
├── tests/              # pytest + Locust
├── docs/               # Rapport Word + PowerPoint soutenance
├── docker-compose.yml
├── Dockerfile.api
├── Makefile
└── requirements.txt
```

---

## Stack technique

| Couche | Technologie | Version |
|---|---|---|
| Langage | Python | 3.12 |
| Analytique | DuckDB + Parquet | 0.10+ |
| Base relationnelle | PostgreSQL + PostGIS | 16 + 3.4 |
| Base NoSQL | MongoDB | 7 |
| API | FastAPI + uvicorn | 0.110+ |
| Geo-join | GeoPandas | 0.14+ |
| Scheduler | APScheduler | 3.10+ |
| Frontend | HTML + MapLibre GL JS | 3.x |
| Infra | Docker Compose | v2 |
| Tests | pytest + Locust | — |

---

## Sources de données (13)

| Source | Indicateur | Format |
|---|---|---|
| DVF (data.gouv.fr) | Prix immobiliers 2021–2024 | CSV annuels .gz |
| RPLS (data.gouv.fr) | Logements sociaux | CSV |
| INSEE Filosofi | Revenus par IRIS | CSV ZIP |
| IDFM | Transports (métro/bus/RER) | API JSON |
| data.education.gouv.fr | Écoles, collèges, lycées | API REST |
| FINESS / SIRENE | Santé (hôpitaux, médecins) | CSV |
| Overpass (OSM) | Parcs et commerces | API REST |
| AIRPARIF | Qualité de l'air | Open data JSON |
| SSMSI (data.gouv.fr) | Criminalité | CSV |
| DRIHL | Loyers de référence | CSV |
| geo.api.gouv.fr | Contours arrondissements | GeoJSON |
| Paris Open Data | Circulation / trafic | API REST |
| BRUITPARIF | Bruit urbain (Lden dB) | Open data JSON |

---

## Batch & Streaming (C2.2)

**Batch nightly DVF** :
```bash
# Lancement manuel (mode one-shot)
venv/bin/python3 pipeline/batch_processor.py

# Mode scheduler (tourne jusqu'à Ctrl+C, s'exécute à 02h00)
venv/bin/python3 pipeline/batch_processor.py --schedule
```

**Streaming micro-batch** :
```bash
make stream                # Démo : 20 batchs, intervalle 1s
make stream-continuous     # Production : continu, intervalle 30s
```

---

## API FastAPI — Endpoints (C2.1)

Tous les endpoints nécessitent le header : `Authorization: urban-explorer-dev-key`

| Endpoint | Source | Description |
|---|---|---|
| `GET /health` | — | Healthcheck |
| `GET /arrondissements` | DuckDB/Gold | 20 arrondissements |
| `GET /prix/{arrondissement}` | DuckDB/Gold | Prix m² (filtre année) |
| `GET /indicateurs/{arrondissement}` | DuckDB/Gold | 4 indicateurs qualité de vie |
| `GET /db/transactions` | PostgreSQL | Transactions DVF filtrables |
| `GET /db/prix-median` | PostgreSQL | Prix médians par arrondissement |
| `GET /db/logements-sociaux` | PostgreSQL | Part logements sociaux (%) |
| `GET /db/proximite` | PostgreSQL/PostGIS | POI dans un rayon (spatial) |
| `GET /mongo/catalog` | MongoDB | Catalogue des 13 sources |
| `GET /batch/status` | Gold JSON | Statut dernier batch nightly |
| `GET /stream/air-quality` | MongoDB | Derniers événements qualité air |

Documentation interactive : http://localhost:8000/docs

---

## Tests

```bash
make test            # Tests unitaires pytest
make test-coverage   # Avec rapport de couverture

# Tests de charge Locust (nécessite l'API démarrée)
venv/bin/locust -f tests/locustfile.py --headless -u 100 -r 10 --run-time 60s \
  -H http://localhost:8000
# Ou interface web : venv/bin/locust -f tests/locustfile.py
```

---

## Documentation soutenance

| Fichier | Contenu |
|---|---|
| [docs/rapport_bloc1_urban_data_explorer.docx](docs/rapport_bloc1_urban_data_explorer.docx) | Rapport Word complet (12 sections, C1.1–C2.4) |
| [docs/presentation_bloc1_urban_data_explorer.pptx](docs/presentation_bloc1_urban_data_explorer.pptx) | Présentation PowerPoint (9 slides) |
| [docs/architecture.md](docs/architecture.md) | Schéma d'architecture technique |
| [docs/databases.md](docs/databases.md) | Schéma PostgreSQL + MongoDB, justifications |
| [docs/batch_streaming.md](docs/batch_streaming.md) | Architecture batch/streaming |
| [docs/data_catalog.md](docs/data_catalog.md) | Catalogue des 13 sources |
