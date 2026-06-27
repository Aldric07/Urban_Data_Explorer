# Bases de données — Urban Data Explorer

> Couvre les compétences RNCP40875 **C1.1** (relationnel), **C1.2** (NoSQL),
> **C1.3** (Data Lake), **C1.4** (scalabilité/résilience) et **C2.1** (API).

## 1. Vue d'ensemble

Le projet utilise **deux bases de données complémentaires** en coexistence
avec le Data Lake Parquet :

| Base | Rôle | Couche | Compétence |
|------|------|--------|------------|
| **PostgreSQL + PostGIS** | Données structurées + géo + requêtes filtrables | Gold | C1.1, C1.3, C1.4 |
| **MongoDB** | Payloads bruts hétérogènes + catalogue + stream | Bronze + meta | C1.2 |
| **Parquet + DuckDB** | Analytique haute perf (existant) | Silver/Gold | C1.3, C2.4 |

Les trois cohabitent : Parquet reste la source analytique rapide, Postgres
sert les requêtes filtrables et spatiales de l'API, Mongo conserve la
traçabilité brute et le catalogue.

```
┌──────────────────────────────────────────────────────────────────────┐
│  13 APIs externes (data.gouv, IDFM, OSM, AIRPARIF, INSEE…)           │
└────────────────────────────┬─────────────────────────────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │   ingestion/         │
                  └──────┬───────────────┘
                         ▼
        ┌────────────────┴────────────────┐
        ▼                                 ▼
┌────────────────┐                ┌────────────────┐
│ data/bronze/   │                │   MongoDB      │
│  CSV/JSON brut │ ──────────────▶│  bronze_raw    │  ← audit & versioning
└───────┬────────┘                │  data_catalog  │  ← métadonnées sources
        ▼                         │  stream_events │  ← TTL 30 j.
┌────────────────┐                └────────────────┘
│ data/silver/   │
│  Parquet clean │
└───────┬────────┘
        ▼
┌────────────────┐                ┌──────────────────────┐
│ data/gold/     │ ──────────────▶│ PostgreSQL + PostGIS │
│  Parquet aggr. │                │  arrondissement      │
└───────┬────────┘                │  transaction_dvf     │
        │                         │  prix_median         │
        │     DuckDB (analytique) │  logement_social     │
        ▼                         │  indicateur          │
   ┌─────────────────────┐        └──────────┬───────────┘
   │   FastAPI (api/)    │ ◀─ SQLAlchemy ────┘
   │                     │ ◀─ pymongo ───────┐
   └──────────┬──────────┘                   │
              ▼                              │
       Dashboard MapLibre              MongoDB ──┘
```

## 2. Justification des choix

### PostgreSQL + PostGIS (C1.1)

- **Données structurées** : arrondissements, transactions, agrégats, indicateurs
  ont un schéma stable connu à l'avance.
- **Intégrité** : contraintes PK / FK / CHECK / UNIQUE garantissent la cohérence
  (un prix ne peut pas exister sans arrondissement, une part de logements
  sociaux est forcément entre 0 et 100…).
- **Requêtes filtrables** : l'API expose des filtres `arrondissement`, `annee`,
  `categorie`. SQL et les index B-tree sont parfaitement adaptés.
- **PostGIS** : géométries des arrondissements (MULTIPOLYGON) et points DVF
  (POINT). Permet les requêtes spatiales (rayon, intersection, distance) — voir
  endpoint `/db/proximite`.
- **Normalisation 3NF** : chaque fait est dans une table dédiée, pas de
  redondance.

### MongoDB (C1.2)

- **Schémas hétérogènes** : les 13 sources ont des structures de payload toutes
  différentes (OSM = arbre Overpass, AIRPARIF = mesures par capteur, INSEE =
  CSV avec colonnes variables). Forcer un schéma relationnel commun ferait
  perdre des informations.
- **Document-oriented** : un fichier source = un document → audit complet
  avec checksum, taille, fraîcheur, exemple de payload.
- **Index TTL natif** : `stream_events` purgé automatiquement après 30 jours,
  pas besoin de cron.
- **Aggregation pipeline** : construction du catalogue avec `$group` + `$max`
  en une seule passe côté serveur.

## 3. Schéma relationnel (PostgreSQL)

```
arrondissement
  PK code (1..20)
  nom, surface_km2, population
  geom (MULTIPOLYGON, SRID 4326)  ◀── PostGIS

transaction_dvf
  PK id (serial)
  FK arrondissement_code → arrondissement.code
  date_mutation, annee, valeur_fonciere, surface_reelle_bati,
  prix_m2, type_local, nb_pieces, adresse
  geom_point (POINT, SRID 4326)   ◀── PostGIS

prix_median
  PK (arrondissement_code, annee)
  FK arrondissement_code → arrondissement.code
  prix_m2_median, prix_m2_moyen, nb_transactions, prix_m2_variation_pct

logement_social
  PK (arrondissement_code, annee)
  FK arrondissement_code → arrondissement.code
  nb_logements_sociaux, part_logements_sociaux_pct (0..100)

indicateur
  PK id (serial)
  FK arrondissement_code → arrondissement.code
  UNIQUE (arrondissement_code, nom, annee)
  nom, categorie ∈ {accessibilite, qualite_vie, securite, economique, autre}
  valeur, unite, annee, source, detail (JSONB)
```

**Index** :
- `ix_arrondissement_geom` GIST sur `arrondissement.geom`
- `ix_dvf_geom` GIST sur `transaction_dvf.geom_point`
- `ix_dvf_arr_annee` B-tree composite
- `ix_prix_annee` B-tree
- `ix_indicateur_categorie` B-tree

## 4. Schéma documentaire (MongoDB)

### `bronze_raw`

```jsonc
{
  "source": "transports_idf_arrets.json",
  "path": "transports_idf_arrets.json",
  "format": "json",
  "size_bytes": 1542301,
  "checksum": "sha256:…",
  "ingested_at": ISODate("2026-05-21T08:42:00Z"),
  "payload_kind": "json",
  "sample": [ /* 5 premiers éléments */ ],
  "payload": { /* présent si < 256 KB */ }
}
```
Index : `(source, ingested_at desc)`, `(source, checksum)`.

### `data_catalog`

```jsonc
{
  "source": "dvf",
  "libelle": "Demandes de Valeurs Foncières",
  "fournisseur": "data.gouv.fr / DGFiP",
  "description": "Transactions immobilières 2021-2024, prix au m²",
  "nb_fichiers": 4,
  "taille_totale_bytes": 12894812,
  "derniere_ingestion": ISODate("…"),
  "formats": ["csv"],
  "qualite": { "fraicheur_jours": 2, "complet": true },
  "updated_at": ISODate("…")
}
```
Index : `source` unique.

### `stream_events`

```jsonc
{
  "arrondissement": 6,
  "annee": 2024,
  "prix_m2_median": 13910,
  "nb_transactions": 412,
  "ingested_at": ISODate("…")
}
```
Index : `ingested_at` TTL 30 j., `(arrondissement, annee desc)`.

## 5. Démarrage rapide

```bash
# 1. Bases en local via Docker
make db-up                       # postgres:5432 + mongo:27017

# 2. (Une fois) ingest + pipeline → Parquet
make ingest && make pipeline

# 3. Charger les bases
make load-db                     # ou load-postgres / load-mongo

# 4. API (utilise PG + Mongo + DuckDB)
make api
# → http://localhost:8000/health
# → http://localhost:8000/db/catalog   (X-API-Key: urban-explorer-dev-key)
```

## 6. Endpoints exposés

### PostgreSQL
- `GET /db/arrondissements` — référentiel
- `GET /db/prix?arrondissement=&annee_min=&annee_max=` — prix médians filtrables
- `GET /db/indicateurs?categorie=accessibilite|qualite_vie|securite|economique`
- `GET /db/proximite?lat=&lon=&rayon_m=` — **requête PostGIS** (transactions
  dans un rayon)

### MongoDB
- `GET /db/catalog` — data catalog complet
- `GET /db/bronze/{source}?limit=` — documents bruts d'une source
- `GET /db/stream?arrondissement=&limit=` — événements de streaming

Toutes les routes `/db/*` requièrent le header `X-API-Key`.

## 7. Performance & tests de charge (C1.1, C1.4, C2.4)

- Pool de connexions SQLAlchemy : `pool_size=10`, `max_overflow=20`,
  `pool_pre_ping=True`.
- Tests de charge avec **Locust** (`tests/locustfile.py`) : couvrir
  `/db/prix`, `/db/proximite`, `/db/catalog`.
- Healthchecks Docker sur les deux bases (`pg_isready`, `mongosh ping`).
- Volumes Docker nommés (`postgres_data`, `mongo_data`) → persistance entre
  redémarrages.

## 8. Sécurité (C1.3)

- Authentification API via `X-API-Key` sur toutes les routes `/db/*`.
- Credentials des bases via `.env` (non commité), surchargés dans
  `docker-compose.yml` pour le dev.
- En production : remplacer `urban_dev_pwd` par un secret managé, restreindre
  les permissions au strict nécessaire (l'API n'a besoin que de `SELECT` sur PG
  et `find` sur Mongo une fois les données chargées).
