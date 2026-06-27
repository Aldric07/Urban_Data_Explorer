"""
api/main.py — Urban Data Explorer
API FastAPI : DuckDB (analytique Parquet) + SQLAlchemy (PostgreSQL/PostGIS)
+ pymongo (MongoDB).
Compétences validées : C2.1 (API), C1.1/C1.2 (exposition des deux bases).
"""
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from sqlalchemy import text

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GOLD_DIR, SILVER_DIR, API_KEY
from db.postgres import get_engine
from db.mongo import bronze, catalog, ping as mongo_ping, stream

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Urban Data Explorer API",
    description="Données du marché immobilier et qualité résidentielle à Paris",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    return key

# ── Helpers ───────────────────────────────────────────────────────────────────
def clean_nan(obj):
    """Remplace récursivement NaN/Inf par None pour JSON."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def query_parquet(path: Path, sql: str) -> list[dict]:
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"Données non disponibles : {path.name}")
    con = duckdb.connect()
    df  = con.execute(sql.format(path=str(path))).df()
    con.close()
    # Remplace NaN pandas par None avant sérialisation JSON
    df = df.where(pd.notnull(df), other=None)
    return clean_nan(df.to_dict(orient="records"))


def gold_path() -> Path:
    return GOLD_DIR / "gold_final.parquet"


def get_ls_col() -> str:
    """Retourne le bon nom de colonne logements sociaux dans gold_final."""
    p = gold_path()
    if not p.exists():
        return "nb_logements_sociaux_x"
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
    con.close()
    # Préférence : colonne sans suffixe, sinon _x
    for name in ["nb_logements_sociaux", "nb_logements_sociaux_x", "nb_logements_sociaux_y"]:
        if name in cols:
            return name
    return cols[0]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    # PostgreSQL : ping rapide
    pg_ok = False
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
            pg_ok = True
    except Exception:
        pg_ok = False
    return {
        "status": "ok",
        "gold_ready": gold_path().exists(),
        "postgres_ready": pg_ok,
        "mongo_ready": mongo_ping(),
        "version": "1.1.0",
    }


@app.get("/arrondissements", dependencies=[Depends(verify_key)])
def list_arrondissements():
    return query_parquet(gold_path(), """
        SELECT DISTINCT
            arrondissement,
            ROUND(AVG(prix_m2_median), 0) AS prix_m2_median_global,
            SUM(nb_transactions)          AS nb_transactions_total
        FROM read_parquet('{path}')
        GROUP BY arrondissement
        ORDER BY arrondissement
    """)


@app.get("/arrondissements/{arr_id}", dependencies=[Depends(verify_key)])
def get_arrondissement(arr_id: int, annee: Optional[int] = None):
    if arr_id not in range(1, 21):
        raise HTTPException(status_code=400, detail="Arrondissement invalide (1-20)")
    where = f"arrondissement = {arr_id}"
    if annee:
        where += f" AND annee = {annee}"
    return query_parquet(gold_path(), f"""
        SELECT * FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY annee
    """)


@app.get("/prix", dependencies=[Depends(verify_key)])
def get_prix(
    arrondissement: Optional[int] = None,
    annee_min: int = Query(2021),
    annee_max: int = Query(2024),
):
    conditions = [f"annee BETWEEN {annee_min} AND {annee_max}"]
    if arrondissement:
        conditions.append(f"arrondissement = {arrondissement}")
    where = " AND ".join(conditions)
    return query_parquet(gold_path(), f"""
        SELECT arrondissement, annee,
               prix_m2_median, prix_m2_moyen,
               nb_transactions, prix_m2_variation_pct
        FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY arrondissement, annee
    """)


@app.get("/prix/evolution", dependencies=[Depends(verify_key)])
def get_evolution_prix():
    return query_parquet(gold_path(), """
        SELECT arrondissement, annee,
               prix_m2_median, nb_transactions,
               prix_m2_variation_pct
        FROM read_parquet('{path}')
        ORDER BY annee, arrondissement
    """)


@app.get("/indicateurs", dependencies=[Depends(verify_key)])
def get_indicateurs(arrondissement: Optional[int] = None):
    path  = GOLD_DIR / "indicateurs_custom.parquet"
    where = f"arrondissement = {arrondissement}" if arrondissement else "1=1"
    return query_parquet(path, f"""
        SELECT * FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY arrondissement
    """)


@app.get("/comparaison", dependencies=[Depends(verify_key)])
def comparer_arrondissements(
    arr1: int = Query(...),
    arr2: int = Query(...),
    annee: int = Query(2023),
):
    for a in [arr1, arr2]:
        if a not in range(1, 21):
            raise HTTPException(status_code=400, detail=f"Arrondissement invalide : {a}")

    ls_col = get_ls_col()
    prix = query_parquet(gold_path(), f"""
        SELECT arrondissement, annee, prix_m2_median, nb_transactions,
               {ls_col} AS nb_logements_sociaux,
               revenu_median, m2_par_revenu_annuel
        FROM read_parquet('{{path}}')
        WHERE arrondissement IN ({arr1}, {arr2}) AND annee = {annee}
    """)
    indic = query_parquet(GOLD_DIR / "indicateurs_custom.parquet", f"""
        SELECT * FROM read_parquet('{{path}}')
        WHERE arrondissement IN ({arr1}, {arr2})
    """)
    return {"arrondissements": [arr1, arr2], "annee": annee,
            "prix": prix, "indicateurs": indic}


@app.get("/geojson", dependencies=[Depends(verify_key)])
def get_geojson():
    import json
    for geo_path in [
        SILVER_DIR / "geo_arrondissements.geojson",
        Path(__file__).parent.parent / "data" / "bronze" / "geo_arrondissements.geojson",
    ]:
        if geo_path.exists():
            return JSONResponse(content=json.loads(geo_path.read_text()))
    raise HTTPException(status_code=503, detail="GeoJSON non disponible")


@app.get("/logements-sociaux", dependencies=[Depends(verify_key)])
def get_logements_sociaux(arrondissement: Optional[int] = None):
    where = f"arrondissement = {arrondissement}" if arrondissement else "1=1"
    # Détecte dynamiquement les colonnes disponibles
    p = gold_path()
    if not p.exists():
        raise HTTPException(status_code=503, detail="Données non disponibles")
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet(\'{p}\')").fetchall()]
    con.close()
    # Colonnes logements sociaux
    nb_col  = next((c for c in ["nb_logements_sociaux","nb_logements_sociaux_x"] if c in cols), None)
    pct_col = next((c for c in ["part_logements_sociaux_pct","part_ls_pct"] if c in cols), None)
    select_parts = ["arrondissement", "annee"]
    if nb_col:  select_parts.append(f"{nb_col} AS nb_logements_sociaux")
    if pct_col: select_parts.append(f"{pct_col} AS part_logements_sociaux_pct")
    if not nb_col and not pct_col:
        return []
    filter_col = nb_col or pct_col
    return query_parquet(p, f"""
        SELECT {", ".join(select_parts)}
        FROM read_parquet('{{path}}')
        WHERE {where} AND {filter_col} IS NOT NULL
        ORDER BY arrondissement, annee
    """)


@app.get("/stream/latest", dependencies=[Depends(verify_key)])
def get_stream_latest():
    path = GOLD_DIR / "stream_consolidated.parquet"
    if not path.exists():
        return {"message": "Streaming non encore lancé", "data": []}
    return {"data": query_parquet(path, "SELECT * FROM read_parquet('{path}') ORDER BY arrondissement")}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints PostgreSQL / PostGIS (C1.1, C2.1)
# Exposent les mêmes données que Parquet mais via le moteur relationnel —
# démontre l'intégration et permet les requêtes SQL filtrables côté serveur.
# ─────────────────────────────────────────────────────────────────────────────

def _sql_rows(sql: str, params: dict | None = None) -> list[dict]:
    """Exécute une requête PG paramétrée et renvoie une liste de dicts."""
    try:
        with get_engine().connect() as conn:
            result = conn.execute(text(sql), params or {})
            cols = result.keys()
            return [
                clean_nan({c: (None if pd.isna(v) else v) for c, v in zip(cols, row)})
                for row in result.fetchall()
            ]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"PostgreSQL indisponible : {e}")


@app.get("/db/arrondissements", dependencies=[Depends(verify_key)])
def db_arrondissements():
    """Liste des 20 arrondissements depuis Postgres (référentiel + surface)."""
    return _sql_rows(
        "SELECT code, nom, surface_km2, population FROM arrondissement ORDER BY code"
    )


@app.get("/db/prix", dependencies=[Depends(verify_key)])
def db_prix(
    arrondissement: Optional[int] = None,
    annee_min: int = Query(2021),
    annee_max: int = Query(2024),
):
    """Prix médians par (arr, année) depuis Postgres — démontre les requêtes
    filtrables côté serveur (C2.1)."""
    sql = """
        SELECT arrondissement_code AS arrondissement, annee,
               prix_m2_median, prix_m2_moyen,
               nb_transactions, prix_m2_variation_pct
        FROM prix_median
        WHERE annee BETWEEN :amin AND :amax
    """
    params = {"amin": annee_min, "amax": annee_max}
    if arrondissement is not None:
        sql += " AND arrondissement_code = :arr"
        params["arr"] = arrondissement
    sql += " ORDER BY arrondissement_code, annee"
    return _sql_rows(sql, params)


@app.get("/db/indicateurs", dependencies=[Depends(verify_key)])
def db_indicateurs(
    arrondissement: Optional[int] = None,
    categorie: Optional[str] = Query(None, description="accessibilite|qualite_vie|securite|economique"),
):
    sql = """
        SELECT arrondissement_code AS arrondissement,
               nom, categorie, valeur, unite, annee, source
        FROM indicateur WHERE 1=1
    """
    params: dict = {}
    if arrondissement is not None:
        sql += " AND arrondissement_code = :arr"
        params["arr"] = arrondissement
    if categorie is not None:
        sql += " AND categorie = :cat"
        params["cat"] = categorie
    sql += " ORDER BY arrondissement_code, categorie, nom"
    return _sql_rows(sql, params)


@app.get("/db/proximite", dependencies=[Depends(verify_key)])
def db_proximite(
    lat: float = Query(..., description="Latitude WGS84"),
    lon: float = Query(..., description="Longitude WGS84"),
    rayon_m: int = Query(500, ge=10, le=5000),
):
    """Requête spatiale PostGIS : transactions DVF dans un rayon autour d'un
    point. Démontre l'usage de PostGIS (C1.1 / extension géospatiale)."""
    sql = """
        SELECT id, arrondissement_code, date_mutation, prix_m2,
               surface_reelle_bati, type_local,
               ST_Distance(
                 geom_point::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
               ) AS distance_m
        FROM transaction_dvf
        WHERE geom_point IS NOT NULL
          AND ST_DWithin(
                geom_point::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :rayon
              )
        ORDER BY distance_m ASC
        LIMIT 200
    """
    return _sql_rows(sql, {"lat": lat, "lon": lon, "rayon": rayon_m})


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints MongoDB (C1.2, C2.1)
# Exposent : catalogue de données, bronze brut (audit), stream temps réel.
# ─────────────────────────────────────────────────────────────────────────────

def _mongo_serialize(docs):
    """Nettoie les ObjectId et datetimes pour JSON."""
    out = []
    for d in docs:
        d.pop("_id", None)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out


@app.get("/db/catalog", dependencies=[Depends(verify_key)])
def db_catalog():
    """Data catalog : sources, libellés, fournisseur, fraîcheur, qualité."""
    try:
        docs = list(catalog().find({}, {"_id": 0}).sort("source", 1))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB indisponible : {e}")
    return _mongo_serialize(docs)


@app.get("/db/bronze/{source}", dependencies=[Depends(verify_key)])
def db_bronze_by_source(source: str, limit: int = Query(20, ge=1, le=100)):
    """Documents Bronze pour une source donnée (audit/traçabilité)."""
    try:
        cur = (
            bronze()
            .find({"source": source}, {"_id": 0, "payload": 0})
            .sort("ingested_at", -1)
            .limit(limit)
        )
        return _mongo_serialize(list(cur))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB indisponible : {e}")


@app.get("/db/stream", dependencies=[Depends(verify_key)])
def db_stream(arrondissement: Optional[int] = None, limit: int = Query(50, ge=1, le=500)):
    """Événements de stream micro-batch (rétention TTL gérée par Mongo)."""
    try:
        q: dict = {}
        if arrondissement is not None:
            q["arrondissement"] = arrondissement
        cur = stream().find(q, {"_id": 0}).sort("ingested_at", -1).limit(limit)
        return _mongo_serialize(list(cur))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB indisponible : {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints Batch & Streaming (C2.2)
# batch_processor.py → /batch/status
# streaming_air_quality.py → /stream/air-quality
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/batch/status")
def get_batch_status():
    """
    Retourne le rapport du dernier batch DVF exécuté.
    Lecture du fichier JSON produit par batch_processor.py.
    """
    report_path = GOLD_DIR / "batch_reports" / "last_report.json"
    if not report_path.exists():
        return {
            "status": "never_run",
            "message": "Aucun batch exécuté — lancer : python3 pipeline/batch_processor.py",
        }
    try:
        report = json.loads(report_path.read_text())
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lecture rapport batch impossible : {exc}")


@app.get("/stream/air-quality", dependencies=[Depends(verify_key)])
def get_air_quality_stream(
    hours: int = Query(24, ge=1, le=168, description="Fenêtre temporelle en heures"),
    alert_only: bool = Query(False, description="Retourner uniquement les arrondissements en alerte"),
):
    """
    Dernières mesures qualité de l'air par arrondissement et alertes actives.

    Données issues de streaming_air_quality.py (collection MongoDB stream_events).
    Agrégat calculé sur la fenêtre glissante demandée (défaut : 24h).
    """
    try:
        col = stream()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Récupère toutes les mesures air quality sur la fenêtre
        raw_docs = list(
            col.find(
                {"type": "air_quality", "ingested_at": {"$gte": cutoff}},
                {"_id": 0},
            ).sort("ingested_at", -1).max_time_ms(5000)
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB indisponible : {exc}")

    if not raw_docs:
        return {
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            "window_hours":  hours,
            "alerts_active": 0,
            "alerts":        [],
            "readings":      [],
            "message":       "Aucune donnée — lancer streaming_air_quality.py",
        }

    # Groupe par arrondissement : dernière mesure + moyenne fenêtre
    by_arr: dict[int, list] = {}
    for doc in raw_docs:
        arr = doc.get("arrondissement")
        if arr and 1 <= arr <= 20:
            by_arr.setdefault(arr, []).append(doc)

    readings = []
    alerts   = []

    for arr in sorted(by_arr):
        docs = by_arr[arr]
        latest = docs[0]  # trié ingested_at desc

        iqa_vals  = [d["iqa"] for d in docs if d.get("iqa") is not None]
        iqa_mean  = round(sum(iqa_vals) / len(iqa_vals), 1) if iqa_vals else None
        iqa_latest = latest.get("iqa")

        alert_level = latest.get("alert_level")
        last_ts     = latest.get("ingested_at") or latest.get("timestamp")
        last_ts_str = last_ts.isoformat() if hasattr(last_ts, "isoformat") else str(last_ts)

        reading = {
            "arrondissement": arr,
            "iqa_latest":     iqa_latest,
            "iqa_mean":       iqa_mean,
            "no2_latest":     latest.get("no2_µg_m3"),
            "pm25_latest":    latest.get("pm25_µg_m3"),
            "alert_level":    alert_level,
            "source":         latest.get("source", "unknown"),
            "last_update":    last_ts_str,
            "n_mesures":      len(docs),
        }
        readings.append(reading)

        if alert_level in ("orange", "rouge"):
            alerts.append({
                "arrondissement": arr,
                "iqa":           iqa_latest,
                "alert_level":   alert_level,
                "no2":           latest.get("no2_µg_m3"),
                "pm25":          latest.get("pm25_µg_m3"),
                "last_update":   last_ts_str,
            })

    if alert_only:
        readings = [r for r in readings if r["alert_level"] in ("orange", "rouge")]

    # Source dominante sur la fenêtre (airparif_live ou bronze_fallback)
    all_sources = [r["source"] for r in readings if r.get("source")]
    dominant_source = max(set(all_sources), key=all_sources.count) if all_sources else "unknown"

    return {
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "window_hours":  hours,
        "alerts_active": len(alerts),
        "alerts":        sorted(alerts, key=lambda a: a["iqa"] or 0, reverse=True),
        "readings":      readings,
        "source":        dominant_source,
    }