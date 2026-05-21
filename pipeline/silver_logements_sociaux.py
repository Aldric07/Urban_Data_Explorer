"""
pipeline/silver_logements_sociaux.py
Bronze → Silver : Logements sociaux Paris.
Fix : lecture directe du CSV de repli APUR avec colonnes connues.
"""
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR

SRC  = BRONZE_DIR / "logements_sociaux_paris.csv"
DEST = SILVER_DIR / "logements_sociaux.parquet"


def run():
    logger.info("Silver logements sociaux (RPLS)…")

    if not SRC.exists():
        logger.warning(f"  {SRC.name} absent — skip")
        return False

    # Lecture avec détection auto du séparateur
    df = None
    for sep in [";", ","]:
        for enc in ["utf-8", "latin-1"]:
            try:
                tmp = pd.read_csv(SRC, sep=sep, encoding=enc)
                if len(tmp.columns) >= 3:
                    df = tmp
                    break
            except Exception:
                continue
        if df is not None:
            break

    if df is None or df.empty:
        logger.error("  Impossible de lire le fichier RPLS")
        return False

    df.columns = df.columns.str.lower().str.strip()
    logger.info(f"  Colonnes disponibles : {list(df.columns)}")

    # Mapping flexible des colonnes
    col_map = {}
    for pattern, alias in [
        (["arrondissement", "arr"],           "arrondissement"),
        (["code_postal", "cp", "postal"],     "code_postal"),
        (["part_ls_pct", "part_ls", "part"],  "part_logements_sociaux_pct"),
        (["nb_logements_sociaux", "nb_log", "nb"], "nb_logements_sociaux"),
        (["annee", "year", "an"],             "annee"),
    ]:
        col = next((c for c in df.columns for p in pattern if p in c), None)
        if col and col not in col_map:
            col_map[col] = alias

    df = df.rename(columns=col_map)
    logger.info(f"  Colonnes après mapping : {list(df.columns)}")

    # Assure que arrondissement est numérique
    if "arrondissement" in df.columns:
        df["arrondissement"] = pd.to_numeric(df["arrondissement"], errors="coerce")
        df = df.dropna(subset=["arrondissement"])
        df["arrondissement"] = df["arrondissement"].astype(int)
        df = df[df["arrondissement"].between(1, 20)]
    else:
        logger.error("  Colonne arrondissement introuvable")
        return False

    # Convertit les colonnes numériques
    for col in ["part_logements_sociaux_pct", "nb_logements_sociaux"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.to_parquet(DEST, index=False)
    logger.success(f"  ✓ {len(df)} arrondissements → {DEST.name}")
    logger.info(f"  Colonnes finales : {list(df.columns)}")

    # Aperçu logements sociaux
    if "part_logements_sociaux_pct" in df.columns:
        logger.info(f"\n{df[['arrondissement','part_logements_sociaux_pct','nb_logements_sociaux']].to_string(index=False)}")

    return True


if __name__ == "__main__":
    run()