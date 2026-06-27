"""
pipeline/load_postgres.py — Charge le Gold (Parquet) dans PostgreSQL + PostGIS.

Pipeline DB :
  1. Initialise le schéma (CREATE TABLE IF NOT EXISTS)
  2. Seed les 20 arrondissements + géométries depuis geo_arrondissements.geojson
  3. Insère / met à jour les agrégats : prix_median, logement_social
  4. Insère les indicateurs custom (qualité de vie, accessibilité…)
  5. (Optionnel) charge un échantillon de transactions DVF

Choix UPSERT (ON CONFLICT) : les exécutions répétées du pipeline ne créent pas
de doublons — le chargement est idempotent.

Compétences couvertes : C1.1 (relationnel normalisé), C1.3 (intégration multi-
sources), C2.3 (transformation), C2.4 (performance via insert bulk).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GOLD_DIR, SILVER_DIR, BRONZE_DIR
from db.postgres import (
    Arrondissement,
    Indicateur,
    LogementSocial,
    PrixMedian,
    TransactionDVF,
    get_engine,
    init_schema,
    session_scope,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _df(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        logger.warning(f"  ⚠ absent : {path.name}")
        return None
    return pd.read_parquet(path)


def _na_to_none(d: dict) -> dict:
    """Pandas NaN → None pour psycopg2."""
    return {k: (None if pd.isna(v) else v) for k, v in d.items()}


def _upsert(session, model, rows: list[dict], pk_cols: list[str]):
    """Bulk UPSERT sur le modèle SQLAlchemy."""
    if not rows:
        return 0
    table = model.__table__
    stmt = pg_insert(table).values(rows)
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name not in pk_cols and not c.primary_key
    }
    if update_cols:
        stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
    result = session.execute(stmt)
    return result.rowcount or len(rows)


# ── Étapes de chargement ────────────────────────────────────────────────────

def seed_arrondissements(session) -> int:
    """Insère les 20 arrondissements + géométries depuis le GeoJSON.

    Format attendu : FeatureCollection avec, par feature :
      - properties.c_ar ou .c_arinsee ou .l_ar (variable selon la source)
      - geometry (Polygon/MultiPolygon en 4326)
    """
    geo_path = SILVER_DIR / "geo_arrondissements.geojson"
    if not geo_path.exists():
        geo_path = BRONZE_DIR / "geo_arrondissements.geojson"
    if not geo_path.exists():
        logger.warning("  ⚠ geo_arrondissements.geojson introuvable — seed minimal")
        rows = [{"code": i, "nom": f"{i}e arrondissement"} for i in range(1, 21)]
        return _upsert(session, Arrondissement, rows, ["code"])

    fc = json.loads(geo_path.read_text())
    rows = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {}) or {}
        # Détection robuste du code (selon l'export OpenData Paris)
        code = (
            props.get("c_ar")
            or props.get("c_arinsee")
            or props.get("code")
            or props.get("arrondissement")
        )
        if code is None:
            continue
        try:
            code_int = int(str(code)[-2:]) if int(code) > 75000 else int(code)
        except (TypeError, ValueError):
            continue
        if not (1 <= code_int <= 20):
            continue

        nom = props.get("l_ar") or props.get("nom") or f"{code_int}e arrondissement"
        surface = props.get("surface") or props.get("surface_km2")
        geom_json = json.dumps(feat["geometry"]) if feat.get("geometry") else None

        rows.append({
            "code": code_int,
            "nom": str(nom)[:64],
            "surface_km2": float(surface) / 1_000_000 if surface else None,
            "geom": geom_json,
        })

    # Upsert avec conversion GeoJSON → geometry via PostGIS
    if not rows:
        return 0
    sql = text("""
        INSERT INTO arrondissement (code, nom, surface_km2, geom)
        VALUES (:code, :nom, :surface_km2,
                CASE WHEN :geom IS NULL THEN NULL
                     ELSE ST_Multi(ST_GeomFromGeoJSON(:geom)) END)
        ON CONFLICT (code) DO UPDATE
        SET nom = EXCLUDED.nom,
            surface_km2 = EXCLUDED.surface_km2,
            geom = EXCLUDED.geom
    """)
    for r in rows:
        session.execute(sql, r)
    return len(rows)


def load_prix_median(session) -> int:
    df = _df(GOLD_DIR / "gold_final.parquet")
    if df is None or df.empty:
        return 0
    cols_needed = {"arrondissement", "annee"}
    if not cols_needed.issubset(df.columns):
        logger.warning(f"  ⚠ gold_final manque {cols_needed - set(df.columns)}")
        return 0

    df = df.rename(columns={"arrondissement": "arrondissement_code"})
    keep = [
        "arrondissement_code", "annee", "prix_m2_median", "prix_m2_moyen",
        "nb_transactions", "prix_m2_variation_pct",
    ]
    df = df[[c for c in keep if c in df.columns]].drop_duplicates(
        subset=["arrondissement_code", "annee"]
    )
    rows = [_na_to_none(r) for r in df.to_dict(orient="records")]
    return _upsert(session, PrixMedian, rows, ["arrondissement_code", "annee"])


def load_logements_sociaux(session) -> int:
    df = _df(GOLD_DIR / "gold_final.parquet")
    if df is None or df.empty:
        return 0
    nb_col = next(
        (c for c in ["nb_logements_sociaux", "nb_logements_sociaux_x"] if c in df.columns),
        None,
    )
    pct_col = next(
        (c for c in ["part_logements_sociaux_pct", "part_ls_pct"] if c in df.columns),
        None,
    )
    if not nb_col and not pct_col:
        return 0

    sub = df[["arrondissement", "annee"]].copy()
    sub["nb_logements_sociaux"] = df[nb_col] if nb_col else None
    sub["part_logements_sociaux_pct"] = df[pct_col] if pct_col else None
    sub = sub.rename(columns={"arrondissement": "arrondissement_code"})
    sub = sub.dropna(subset=["arrondissement_code", "annee"]).drop_duplicates(
        subset=["arrondissement_code", "annee"]
    )
    rows = [_na_to_none(r) for r in sub.to_dict(orient="records")]
    return _upsert(session, LogementSocial, rows, ["arrondissement_code", "annee"])


def load_indicateurs(session) -> int:
    """Charge les indicateurs custom (forme longue : 1 ligne par couple arr×nom)."""
    df = _df(GOLD_DIR / "indicateurs_custom.parquet")
    if df is None or df.empty:
        return 0

    # Stratégie : si le parquet est en format large (1 ligne par arr, 1 col par
    # indicateur), on melt en format long. Sinon on l'utilise tel quel.
    if {"nom", "valeur", "arrondissement"}.issubset(df.columns):
        long_df = df.copy()
    else:
        id_cols = [c for c in ["arrondissement", "annee"] if c in df.columns]
        value_cols = [c for c in df.columns if c not in id_cols]
        long_df = df.melt(
            id_vars=id_cols,
            value_vars=value_cols,
            var_name="nom",
            value_name="valeur",
        )

    long_df = long_df.rename(columns={"arrondissement": "arrondissement_code"})
    long_df = long_df.dropna(subset=["valeur"])

    # Catégorisation simple par nom (préfixe / mots-clés)
    def categorize(name: str) -> str:
        n = name.lower()
        if any(k in n for k in ["transport", "metro", "rer", "bus", "acces"]):
            return "accessibilite"
        if any(k in n for k in ["air", "bruit", "parc", "jardin", "pollution", "circulation"]):
            return "qualite_vie"
        if any(k in n for k in ["crim", "delit", "incident", "securite"]):
            return "securite"
        if any(k in n for k in ["prix", "loyer", "revenu", "ls", "social"]):
            return "economique"
        return "autre"

    long_df["categorie"] = long_df["nom"].astype(str).map(categorize)
    if "annee" not in long_df.columns:
        long_df["annee"] = None

    rows = []
    for r in long_df.to_dict(orient="records"):
        rows.append({
            "arrondissement_code": int(r["arrondissement_code"]),
            "nom": str(r["nom"])[:64],
            "categorie": r["categorie"],
            "valeur": float(r["valeur"]) if pd.notna(r["valeur"]) else None,
            "annee": int(r["annee"]) if pd.notna(r.get("annee")) else None,
            "unite": None,
            "source": "gold/indicateurs_custom",
            "detail": None,
        })

    # UPSERT sur (arrondissement_code, nom, annee)
    table = Indicateur.__table__
    stmt = pg_insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["arrondissement_code", "nom", "annee"],
        set_={
            "valeur": stmt.excluded.valeur,
            "categorie": stmt.excluded.categorie,
            "source": stmt.excluded.source,
        },
    )
    session.execute(stmt)
    return len(rows)


def load_transactions_sample(session, max_rows: int = 50_000) -> int:
    """Charge un échantillon de transactions DVF (silver) pour démos/tests."""
    silver_dvf = SILVER_DIR / "dvf"
    if not silver_dvf.exists():
        return 0

    files = list(silver_dvf.glob("*.parquet"))
    if not files:
        return 0

    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if df.empty:
        return 0

    # Normalisation des noms de colonnes (DVF a beaucoup d'alias possibles)
    col_map = {
        "code_postal": "code_postal",
        "valeur_fonciere": "valeur_fonciere",
        "surface_reelle_bati": "surface_reelle_bati",
        "prix_m2": "prix_m2",
        "type_local": "type_local",
        "nombre_pieces_principales": "nb_pieces",
        "nb_pieces": "nb_pieces",
        "date_mutation": "date_mutation",
        "arrondissement": "arrondissement_code",
        "longitude": "lon",
        "latitude": "lat",
        "adresse_nom_voie": "voie",
        "adresse_numero": "numero",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    if "arrondissement_code" not in df.columns and "code_postal" in df.columns:
        df["arrondissement_code"] = (
            df["code_postal"].astype(str).str[-3:].str.lstrip("0").replace("", "0").astype(int, errors="ignore")
        )

    if "date_mutation" in df.columns:
        df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")
        df["annee"] = df["date_mutation"].dt.year

    df = df[df["arrondissement_code"].between(1, 20, inclusive="both")]
    df = df.head(max_rows)

    rows = []
    for r in df.to_dict(orient="records"):
        if pd.isna(r.get("arrondissement_code")) or pd.isna(r.get("date_mutation")):
            continue
        lon, lat = r.get("lon"), r.get("lat")
        geom_pt = (
            f"SRID=4326;POINT({lon} {lat})"
            if pd.notna(lon) and pd.notna(lat)
            else None
        )
        adresse_parts = [str(r[k]) for k in ("numero", "voie") if pd.notna(r.get(k))]
        rows.append(_na_to_none({
            "arrondissement_code": int(r["arrondissement_code"]),
            "date_mutation": r["date_mutation"].date(),
            "annee": int(r["annee"]),
            "valeur_fonciere": r.get("valeur_fonciere"),
            "surface_reelle_bati": r.get("surface_reelle_bati"),
            "prix_m2": r.get("prix_m2"),
            "type_local": str(r["type_local"])[:32] if pd.notna(r.get("type_local")) else None,
            "nb_pieces": int(r["nb_pieces"]) if pd.notna(r.get("nb_pieces")) else None,
            "adresse": " ".join(adresse_parts) if adresse_parts else None,
            "geom_point": geom_pt,
        }))

    if not rows:
        return 0

    # Insert direct (pas d'UPSERT car pas de clé naturelle stable)
    # On vide d'abord pour idempotence
    session.execute(text("TRUNCATE TABLE transaction_dvf RESTART IDENTITY"))
    chunk = 5_000
    for i in range(0, len(rows), chunk):
        session.execute(TransactionDVF.__table__.insert(), rows[i:i + chunk])
    return len(rows)


# ── Orchestration ──────────────────────────────────────────────────────────

def main():
    logger.info("──────────────────────────────────────────────")
    logger.info("  Chargement Gold → PostgreSQL + PostGIS")
    logger.info("──────────────────────────────────────────────")

    logger.info("1. Initialisation schéma (CREATE TABLE IF NOT EXISTS)")
    init_schema()
    logger.info("   ✓ schéma prêt")

    with session_scope() as s:
        logger.info("2. Seed arrondissements + géométries")
        n = seed_arrondissements(s)
        logger.info(f"   ✓ {n} arrondissements")

        logger.info("3. Chargement prix médian par (arr, année)")
        n = load_prix_median(s)
        logger.info(f"   ✓ {n} lignes prix_median")

        logger.info("4. Chargement logements sociaux")
        n = load_logements_sociaux(s)
        logger.info(f"   ✓ {n} lignes logement_social")

        logger.info("5. Chargement indicateurs custom")
        n = load_indicateurs(s)
        logger.info(f"   ✓ {n} lignes indicateur")

        logger.info("6. Chargement échantillon transactions DVF")
        n = load_transactions_sample(s)
        logger.info(f"   ✓ {n} transactions")

    logger.info("✓ Chargement PostgreSQL terminé")


if __name__ == "__main__":
    main()
