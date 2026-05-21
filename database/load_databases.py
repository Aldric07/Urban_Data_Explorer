"""
database/load_databases.py
Charge les données Gold dans PostgreSQL (relationnel) et MongoDB (NoSQL).
Usage : python3 database/load_databases.py
Compétences validées : C1.1 (PostgreSQL), C1.2 (MongoDB)
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GOLD_DIR, SILVER_DIR

# ── Connexion PostgreSQL ───────────────────────────────────────────────
def get_pg_conn():
    import psycopg2
    return psycopg2.connect(
        host="localhost", port=5432,
        dbname="urban_data_explorer",
        user="ude_user", password="ude_password"
    )

# ── Connexion MongoDB ──────────────────────────────────────────────────
def get_mongo_db():
    from pymongo import MongoClient
    client = MongoClient(
        "mongodb://ude_user:ude_password@localhost:27017/urban_data_explorer?authSource=admin"
    )
    return client["urban_data_explorer"]


# ══════════════════════════════════════════════════════════════════════
# POSTGRESQL — Chargement données relationnelles
# ══════════════════════════════════════════════════════════════════════

def load_postgres():
    logger.info("Chargement PostgreSQL…")
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
    except Exception as e:
        logger.error(f"  Connexion PostgreSQL impossible : {e}")
        logger.info("  → Lance d'abord : docker compose up -d postgres")
        return False

    # ── Prix immobiliers (Gold DVF) ────────────────────────────────────
    gold_path = GOLD_DIR / "gold_final.parquet"
    if gold_path.exists():
        df = pd.read_parquet(gold_path)
        n = 0
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO prix_immobiliers
                    (arrondissement_id, annee, prix_m2_median, prix_m2_moyen,
                     nb_transactions, surface_mediane,
                     nb_appartements, nb_maisons, prix_m2_variation_pct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (arrondissement_id, annee) DO UPDATE SET
                    prix_m2_median        = EXCLUDED.prix_m2_median,
                    prix_m2_moyen         = EXCLUDED.prix_m2_moyen,
                    nb_transactions       = EXCLUDED.nb_transactions,
                    prix_m2_variation_pct = EXCLUDED.prix_m2_variation_pct
            """, (
                int(row["arrondissement"]),
                int(row["annee"]),
                float(row["prix_m2_median"])    if pd.notna(row.get("prix_m2_median"))    else None,
                float(row["prix_m2_moyen"])     if pd.notna(row.get("prix_m2_moyen"))     else None,
                int(row["nb_transactions"])     if pd.notna(row.get("nb_transactions"))   else None,
                float(row["surface_mediane"])   if pd.notna(row.get("surface_mediane"))   else None,
                int(row.get("Appartement", 0)) if pd.notna(row.get("Appartement", 0))    else 0,
                int(row.get("Maison", 0))       if pd.notna(row.get("Maison", 0))         else 0,
                float(row["prix_m2_variation_pct"]) if pd.notna(row.get("prix_m2_variation_pct")) else None,
            ))
            n += 1
        conn.commit()
        logger.success(f"  ✓ prix_immobiliers : {n} lignes insérées")

    # ── Logements sociaux ──────────────────────────────────────────────
    ls_path = SILVER_DIR / "logements_sociaux.parquet"
    if ls_path.exists():
        df_ls = pd.read_parquet(ls_path)
        n = 0
        for _, row in df_ls.iterrows():
            annee = int(row["annee"]) if "annee" in row and pd.notna(row["annee"]) else 2022
            cur.execute("""
                INSERT INTO logements_sociaux
                    (arrondissement_id, annee, nb_logements_sociaux, part_logements_sociaux_pct)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (arrondissement_id, annee) DO UPDATE SET
                    nb_logements_sociaux       = EXCLUDED.nb_logements_sociaux,
                    part_logements_sociaux_pct = EXCLUDED.part_logements_sociaux_pct
            """, (
                int(row["arrondissement"]),
                annee,
                int(row["nb_logements_sociaux"])        if pd.notna(row.get("nb_logements_sociaux"))       else None,
                float(row["part_logements_sociaux_pct"]) if pd.notna(row.get("part_logements_sociaux_pct")) else None,
            ))
            n += 1
        conn.commit()
        logger.success(f"  ✓ logements_sociaux : {n} lignes insérées")

    # ── Revenus INSEE ──────────────────────────────────────────────────
    rev_path = SILVER_DIR / "revenus.parquet"
    if rev_path.exists():
        df_rev = pd.read_parquet(rev_path)
        n = 0
        for _, row in df_rev.iterrows():
            annee = int(row["annee"]) if "annee" in row and pd.notna(row.get("annee")) else 2021
            cur.execute("""
                INSERT INTO revenus (arrondissement_id, annee, revenu_median, taux_pauvrete)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (arrondissement_id, annee) DO UPDATE SET
                    revenu_median = EXCLUDED.revenu_median,
                    taux_pauvrete = EXCLUDED.taux_pauvrete
            """, (
                int(row["arrondissement"]),
                annee,
                float(row["revenu_median"])   if pd.notna(row.get("revenu_median"))  else None,
                float(row["taux_pauvrete"])   if pd.notna(row.get("taux_pauvrete"))  else None,
            ))
            n += 1
        conn.commit()
        logger.success(f"  ✓ revenus : {n} lignes insérées")

    cur.close()
    conn.close()
    logger.success("  ✓ PostgreSQL chargé")
    return True


# ══════════════════════════════════════════════════════════════════════
# MONGODB — Chargement données semi-structurées
# ══════════════════════════════════════════════════════════════════════

def load_mongodb():
    logger.info("Chargement MongoDB…")
    try:
        db = get_mongo_db()
    except Exception as e:
        logger.error(f"  Connexion MongoDB impossible : {e}")
        logger.info("  → Lance d'abord : docker compose up -d mongodb")
        return False

    # ── Indicateurs custom ─────────────────────────────────────────────
    indic_path = GOLD_DIR / "indicateurs_custom.parquet"
    if indic_path.exists():
        df = pd.read_parquet(indic_path)
        df = df.where(pd.notnull(df), None)
        docs = df.to_dict(orient="records")
        for doc in docs:
            doc["arrondissement"] = int(doc["arrondissement"])
            doc["updated_at"] = datetime.now(timezone.utc)
            # Convertit numpy float64 → float Python
            for k, v in doc.items():
                if hasattr(v, "item"):
                    doc[k] = v.item()
            db.indicateurs_custom.replace_one(
                {"arrondissement": doc["arrondissement"]},
                doc,
                upsert=True
            )
        logger.success(f"  ✓ indicateurs_custom : {len(docs)} documents upsertés")

    # ── Environnement (air, bruit, circulation) ────────────────────────
    env_sources = {
        "qualite_air":  SILVER_DIR / "qualite_air.parquet",
        "bruit":        SILVER_DIR / "bruit.parquet",
        "circulation":  SILVER_DIR / "circulation.parquet",
    }

    env_by_arr = {}
    for source_name, path in env_sources.items():
        if path.exists():
            df = pd.read_parquet(path)
            df = df.where(pd.notnull(df), None)
            for _, row in df.iterrows():
                arr = int(row["arrondissement"])
                if arr not in env_by_arr:
                    env_by_arr[arr] = {"arrondissement": arr}
                data = {k: (v.item() if hasattr(v, "item") else v)
                        for k, v in row.items() if k != "arrondissement" and v is not None}
                env_by_arr[arr][source_name] = data

    if env_by_arr:
        for arr, doc in env_by_arr.items():
            doc["updated_at"] = datetime.now(timezone.utc)
            db.environnement.replace_one(
                {"arrondissement": arr}, doc, upsert=True
            )
        logger.success(f"  ✓ environnement : {len(env_by_arr)} documents upsertés")

    # ── Points d'intérêt (transports, écoles, parcs) ───────────────────
    poi_sources = [
        ("transport", SILVER_DIR / "transports.parquet",  "lat", "lon"),
        ("ecole",     SILVER_DIR / "education.parquet",   "lat", "lon"),
        ("parc",      SILVER_DIR / "parcs.parquet",       "lat", "lon"),
    ]

    total_poi = 0
    for categorie, path, lat_col, lon_col in poi_sources:
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df.where(pd.notnull(df), None)
        docs = []
        for _, row in df.iterrows():
            lat = row.get(lat_col)
            lon = row.get(lon_col)
            if lat is None or lon is None:
                continue
            doc = {
                "categorie":    categorie,
                "arrondissement": int(row["arrondissement"]) if pd.notna(row.get("arrondissement")) else None,
                "nom":          str(row.get("nom", "") or row.get("name", "")),
                "location": {
                    "type":        "Point",
                    "coordinates": [float(lon), float(lat)]  # GeoJSON : [lon, lat]
                },
                "updated_at": datetime.now(timezone.utc),
            }
            # Champs supplémentaires selon la source
            for extra in ["type", "statut", "mode"]:
                if extra in row and row[extra] is not None:
                    doc[extra] = str(row[extra])
            docs.append(doc)

        if docs:
            # Supprime anciens docs de cette catégorie, réinsère
            db.points_interet.delete_many({"categorie": categorie})
            db.points_interet.insert_many(docs)
            total_poi += len(docs)
            logger.info(f"    {categorie} : {len(docs)} points insérés")

    if total_poi:
        logger.success(f"  ✓ points_interet : {total_poi} documents insérés")

    logger.success("  ✓ MongoDB chargé")
    return True


# ══════════════════════════════════════════════════════════════════════
# VÉRIFICATION
# ══════════════════════════════════════════════════════════════════════

def verify_databases():
    logger.info("Vérification des bases…")

    # PostgreSQL
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        for table in ["arrondissements", "prix_immobiliers", "logements_sociaux", "revenus"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            logger.info(f"  PG  {table:<30} : {count:>5} lignes")
        # Test vue
        cur.execute("SELECT COUNT(*) FROM vue_tableau_bord")
        logger.success(f"  PG  vue_tableau_bord               : {cur.fetchone()[0]:>5} lignes ✓")
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"  PostgreSQL vérification : {e}")

    # MongoDB
    try:
        db = get_mongo_db()
        for coll in ["indicateurs_custom", "environnement", "points_interet", "stream_events"]:
            count = db[coll].count_documents({})
            logger.info(f"  MDB {coll:<30} : {count:>5} documents")
        logger.success("  MongoDB OK ✓")
    except Exception as e:
        logger.warning(f"  MongoDB vérification : {e}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("  Urban Data Explorer — Chargement bases de données")
    logger.info("=" * 60)

    t0 = time.time()
    pg_ok  = load_postgres()
    mdb_ok = load_mongodb()
    verify_databases()

    logger.info(f"\n  PostgreSQL : {'✓' if pg_ok  else '✗'}")
    logger.info(f"  MongoDB    : {'✓' if mdb_ok else '✗'}")
    logger.info(f"  Durée      : {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()