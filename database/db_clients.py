"""
database/db_clients.py
Clients PostgreSQL et MongoDB pour l'API FastAPI.
Connexions lazy avec fallback sur Parquet si les BDD sont indisponibles.
Compétences validées : C1.1, C1.2
"""
import os
from pathlib import Path
from typing import Optional
from loguru import logger

# ── Configuration ──────────────────────────────────────────────────────
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://ude_user:ude_password@localhost:5432/urban_data_explorer"
)
MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb://ude_user:ude_password@localhost:27017/urban_data_explorer?authSource=admin"
)

# ── Clients (initialisés au premier appel) ─────────────────────────────
_pg_pool   = None
_mongo_db  = None


def get_postgres():
    """Retourne une connexion PostgreSQL (psycopg2). None si indisponible."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    try:
        import psycopg2
        from psycopg2 import pool
        _pg_pool = pool.SimpleConnectionPool(1, 5, POSTGRES_URL)
        logger.info("  ✓ PostgreSQL connecté")
        return _pg_pool
    except Exception as e:
        logger.warning(f"  PostgreSQL indisponible ({e}) — fallback Parquet")
        return None


def get_mongodb():
    """Retourne la base MongoDB. None si indisponible."""
    global _mongo_db
    if _mongo_db is not None:
        return _mongo_db
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        _mongo_db = client["urban_data_explorer"]
        logger.info("  ✓ MongoDB connecté")
        return _mongo_db
    except Exception as e:
        logger.warning(f"  MongoDB indisponible ({e}) — fallback Parquet")
        return None


# ── Requêtes PostgreSQL ────────────────────────────────────────────────

def pg_query(sql: str, params: tuple = ()) -> list[dict]:
    """Exécute une requête SELECT PostgreSQL et retourne une liste de dicts."""
    pool = get_postgres()
    if pool is None:
        return []
    conn = pool.getconn()
    try:
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def pg_get_prix(arrondissement: Optional[int] = None,
                annee_min: int = 2021, annee_max: int = 2024) -> list[dict]:
    """Prix immobiliers depuis PostgreSQL."""
    where = "annee BETWEEN %s AND %s"
    params = [annee_min, annee_max]
    if arrondissement:
        where += " AND arrondissement_id = %s"
        params.append(arrondissement)
    return pg_query(f"""
        SELECT arrondissement_id AS arrondissement, annee,
               prix_m2_median, prix_m2_moyen, nb_transactions,
               prix_m2_variation_pct
        FROM prix_immobiliers
        WHERE {where}
        ORDER BY arrondissement_id, annee
    """, tuple(params))


def pg_get_tableau_bord(arrondissement: Optional[int] = None,
                         annee: Optional[int] = None) -> list[dict]:
    """Vue tableau de bord depuis PostgreSQL (jointure automatique)."""
    conditions = []
    params = []
    if arrondissement:
        conditions.append("arrondissement = %s")
        params.append(arrondissement)
    if annee:
        conditions.append("annee = %s")
        params.append(annee)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return pg_query(f"SELECT * FROM vue_tableau_bord {where} ORDER BY arrondissement, annee",
                    tuple(params))


# ── Requêtes MongoDB ───────────────────────────────────────────────────

def mongo_get_indicateurs(arrondissement: Optional[int] = None) -> list[dict]:
    """Indicateurs custom depuis MongoDB."""
    db = get_mongodb()
    if db is None:
        return []
    query = {}
    if arrondissement:
        query["arrondissement"] = arrondissement
    docs = list(db.indicateurs_custom.find(query, {"_id": 0, "updated_at": 0}))
    return docs


def mongo_get_environnement(arrondissement: Optional[int] = None) -> list[dict]:
    """Données environnementales depuis MongoDB."""
    db = get_mongodb()
    if db is None:
        return []
    query = {}
    if arrondissement:
        query["arrondissement"] = arrondissement
    docs = list(db.environnement.find(query, {"_id": 0, "updated_at": 0}))
    return docs


def mongo_get_poi_near(lat: float, lon: float,
                        max_distance_m: int = 1000,
                        categorie: Optional[str] = None) -> list[dict]:
    """
    Points d'intérêt proches d'un point GPS (requête géospatiale MongoDB).
    Exemple : trouver les transports à moins de 500m d'une adresse.
    """
    db = get_mongodb()
    if db is None:
        return []
    query = {
        "location": {
            "$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                "$maxDistance": max_distance_m
            }
        }
    }
    if categorie:
        query["categorie"] = categorie
    return list(db.points_interet.find(query, {"_id": 0}).limit(50))


def mongo_log_stream_event(batch_id: int, arrondissement: int,
                            prix_m2_median: float, nb_transactions: int):
    """Enregistre un événement de streaming dans MongoDB."""
    from datetime import datetime, timezone
    db = get_mongodb()
    if db is None:
        return
    db.stream_events.insert_one({
        "batch_id":        batch_id,
        "arrondissement":  arrondissement,
        "prix_m2_median":  prix_m2_median,
        "nb_transactions": nb_transactions,
        "timestamp":       datetime.now(timezone.utc),
    })


def check_connections() -> dict:
    """Vérifie l'état des deux connexions. Utilisé par /health."""
    pg  = get_postgres() is not None
    mdb = get_mongodb()  is not None
    return {
        "postgresql": "connected" if pg  else "unavailable (fallback parquet)",
        "mongodb":    "connected" if mdb else "unavailable (fallback parquet)",
    }