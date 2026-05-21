"""
api/main.py — Urban Data Explorer
API FastAPI avec PostgreSQL (C1.1) + MongoDB (C1.2) + fallback Parquet.
Compétences validées : C1.1, C1.2, C2.1
"""
import math
import sys
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GOLD_DIR, SILVER_DIR, API_KEY

# Import couche BDD (avec fallback gracieux si non installé)
try:
    from database.db_clients import (
        pg_get_prix, pg_get_tableau_bord,
        mongo_get_indicateurs, mongo_get_environnement,
        mongo_get_poi_near, mongo_log_stream_event,
        check_connections,
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Urban Data Explorer API",
    description="Données marché immobilier Paris — PostgreSQL + MongoDB + Parquet",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Auth ──────────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    return key

# ── Helpers ───────────────────────────────────────────────────────────
def clean_nan(obj):
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
    df  = df.where(pd.notnull(df), other=None)
    return clean_nan(df.to_dict(orient="records"))

def gold_path() -> Path:
    return GOLD_DIR / "gold_final.parquet"

def get_ls_col() -> str:
    p = gold_path()
    if not p.exists():
        return "nb_logements_sociaux_x"
    con  = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
    con.close()
    for name in ["part_logements_sociaux_pct", "nb_logements_sociaux", "nb_logements_sociaux_x"]:
        if name in cols:
            return name
    return cols[0]

# ── Endpoints ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    db_status = check_connections() if DB_AVAILABLE else {
        "postgresql": "module non installé",
        "mongodb":    "module non installé"
    }
    return {
        "status":     "ok",
        "gold_ready": gold_path().exists(),
        "version":    "2.0.0",
        "databases":  db_status,
    }


@app.get("/prix", dependencies=[Depends(verify_key)])
def get_prix(
    arrondissement: Optional[int] = None,
    annee_min: int = Query(2021),
    annee_max: int = Query(2024),
):
    """
    Prix/m² par arrondissement × année.
    Source : PostgreSQL si disponible, sinon Parquet Gold.
    """
    if DB_AVAILABLE:
        try:
            result = pg_get_prix(arrondissement, annee_min, annee_max)
            if result:
                return clean_nan(result)
        except Exception as e:
            pass  # Fallback Parquet

    conditions = [f"annee BETWEEN {annee_min} AND {annee_max}"]
    if arrondissement:
        conditions.append(f"arrondissement = {arrondissement}")
    where = " AND ".join(conditions)
    return query_parquet(gold_path(), f"""
        SELECT arrondissement, annee, prix_m2_median, prix_m2_moyen,
               nb_transactions, prix_m2_variation_pct
        FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY arrondissement, annee
    """)


@app.get("/prix/evolution", dependencies=[Depends(verify_key)])
def get_evolution_prix():
    """Évolution du prix/m² — source PostgreSQL ou Parquet."""
    if DB_AVAILABLE:
        try:
            result = pg_get_prix()
            if result:
                return clean_nan(result)
        except Exception:
            pass

    return query_parquet(gold_path(), """
        SELECT arrondissement, annee, prix_m2_median,
               nb_transactions, prix_m2_variation_pct
        FROM read_parquet('{path}')
        ORDER BY annee, arrondissement
    """)


@app.get("/indicateurs", dependencies=[Depends(verify_key)])
def get_indicateurs(arrondissement: Optional[int] = None):
    """
    4 indicateurs custom + score global.
    Source : MongoDB si disponible, sinon Parquet Gold.
    """
    if DB_AVAILABLE:
        try:
            result = mongo_get_indicateurs(arrondissement)
            if result:
                return clean_nan(result)
        except Exception:
            pass

    path  = GOLD_DIR / "indicateurs_custom.parquet"
    where = f"arrondissement = {arrondissement}" if arrondissement else "1=1"
    return query_parquet(path, f"""
        SELECT * FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY arrondissement
    """)


@app.get("/environnement", dependencies=[Depends(verify_key)])
def get_environnement(arrondissement: Optional[int] = None):
    """
    Données environnementales (air, bruit, circulation).
    Source : MongoDB exclusivement (données semi-structurées).
    """
    if DB_AVAILABLE:
        try:
            result = mongo_get_environnement(arrondissement)
            if result:
                return clean_nan(result)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"MongoDB indisponible : {e}")
    raise HTTPException(status_code=503, detail="MongoDB requis pour cet endpoint")


@app.get("/poi/nearby", dependencies=[Depends(verify_key)])
def get_poi_nearby(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    distance_m: int = Query(500, description="Rayon en mètres"),
    categorie: Optional[str] = Query(None, description="transport, ecole, parc"),
):
    """
    Points d'intérêt proches d'un point GPS.
    Requête géospatiale MongoDB ($nearSphere).
    Source : MongoDB exclusivement (index 2dsphere).
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="MongoDB requis")
    try:
        result = mongo_get_poi_near(lat, lon, distance_m, categorie)
        return clean_nan(result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/arrondissements", dependencies=[Depends(verify_key)])
def list_arrondissements():
    """Tableau de bord complet — source PostgreSQL (vue jointure) ou Parquet."""
    if DB_AVAILABLE:
        try:
            result = pg_get_tableau_bord()
            if result:
                return clean_nan(result)
        except Exception:
            pass

    return query_parquet(gold_path(), """
        SELECT DISTINCT arrondissement,
               ROUND(AVG(prix_m2_median), 0) AS prix_m2_median_global,
               SUM(nb_transactions)           AS nb_transactions_total
        FROM read_parquet('{path}')
        GROUP BY arrondissement
        ORDER BY arrondissement
    """)


@app.get("/arrondissements/{arr_id}", dependencies=[Depends(verify_key)])
def get_arrondissement(arr_id: int, annee: Optional[int] = None):
    if arr_id not in range(1, 21):
        raise HTTPException(status_code=400, detail="Arrondissement invalide (1-20)")

    if DB_AVAILABLE:
        try:
            result = pg_get_tableau_bord(arr_id, annee)
            if result:
                return clean_nan(result)
        except Exception:
            pass

    where = f"arrondissement = {arr_id}"
    if annee:
        where += f" AND annee = {annee}"
    return query_parquet(gold_path(), f"""
        SELECT * FROM read_parquet('{{path}}')
        WHERE {where}
        ORDER BY annee
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

    # Indicateurs depuis MongoDB si dispo
    indic = []
    if DB_AVAILABLE:
        try:
            for arr in [arr1, arr2]:
                docs = mongo_get_indicateurs(arr)
                indic.extend(docs)
        except Exception:
            pass
    if not indic:
        indic = query_parquet(GOLD_DIR / "indicateurs_custom.parquet", f"""
            SELECT * FROM read_parquet('{{path}}')
            WHERE arrondissement IN ({arr1}, {arr2})
        """)

    return {
        "arrondissements": [arr1, arr2],
        "annee": annee,
        "prix": prix,
        "indicateurs": indic,
    }


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
    p = gold_path()
    if not p.exists():
        raise HTTPException(status_code=503, detail="Données non disponibles")
    con  = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{p}')").fetchall()]
    con.close()
    nb_col  = next((c for c in ["nb_logements_sociaux","nb_logements_sociaux_x"] if c in cols), None)
    pct_col = next((c for c in ["part_logements_sociaux_pct","part_ls_pct"] if c in cols), None)
    select_parts = ["arrondissement", "annee"]
    if nb_col:  select_parts.append(f"{nb_col} AS nb_logements_sociaux")
    if pct_col: select_parts.append(f"{pct_col} AS part_logements_sociaux_pct")
    if not nb_col and not pct_col:
        return []
    filter_col = nb_col or pct_col
    where = f"arrondissement = {arrondissement}" if arrondissement else "1=1"
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
    return {"data": query_parquet(path,
        "SELECT * FROM read_parquet('{path}') ORDER BY arrondissement")}