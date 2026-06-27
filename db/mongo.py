"""
db/mongo.py — Client MongoDB (C1.2)

Collections :
- bronze_raw      : payloads JSON bruts des 13 APIs (un document par snapshot,
                    schémas hétérogènes — c'est précisément ce que NoSQL gère bien)
- data_catalog    : métadonnées des sources (URL, schéma observé, fraîcheur, qualité)
- stream_events   : événements du streaming micro-batch (TTL court possible)

Choix MongoDB justifié :
- Schémas non-figés des APIs externes (OSM, AIRPARIF, IDFM, INSEE… chacune ses
  champs) → un modèle relationnel rigide forcerait à projeter chaque payload
  vers un schéma commun avant ingestion, ce qui ferait perdre des informations.
- Requêtes par clé/source/date suffisent pour la couche Bronze (pas de jointures).
- Index TTL natif pour purger les événements de stream automatiquement.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from datetime import timezone

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MONGO_DB_NAME, MONGO_URI

# Noms de collections (constantes pour ne pas dupliquer ailleurs)
COL_BRONZE = "bronze_raw"
COL_CATALOG = "data_catalog"
COL_STREAM = "stream_events"

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Singleton du client Mongo."""
    global _client
    if _client is None:
        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            socketTimeoutMS=5000,
            retryWrites=True,
            tz_aware=True,            # datetimes renvoyés en UTC aware
            tzinfo=timezone.utc,
        )
    return _client


def get_db() -> Database:
    return get_client()[MONGO_DB_NAME]


def bronze() -> Collection:
    return get_db()[COL_BRONZE]


def catalog() -> Collection:
    return get_db()[COL_CATALOG]


def stream() -> Collection:
    return get_db()[COL_STREAM]


def init_indexes() -> None:
    """Crée les index nécessaires (idempotent)."""
    db = get_db()

    # Bronze : recherche par source + tri par fraîcheur
    db[COL_BRONZE].create_index([("source", ASCENDING), ("ingested_at", DESCENDING)])
    db[COL_BRONZE].create_index([("source", ASCENDING), ("checksum", ASCENDING)], unique=False)

    # Catalogue : une entrée par source (unique)
    db[COL_CATALOG].create_index([("source", ASCENDING)], unique=True)

    # Stream : index TTL 30 jours sur ingested_at + lookup arrondissement/année
    db[COL_STREAM].create_index(
        [("ingested_at", ASCENDING)],
        expireAfterSeconds=30 * 24 * 3600,
    )
    db[COL_STREAM].create_index(
        [("arrondissement", ASCENDING), ("annee", DESCENDING)]
    )


def ping() -> bool:
    """Healthcheck simple."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
