"""
pipeline/silver_revenus.py
Bronze → Silver : Nettoyage des revenus médians INSEE Filosofi.
Produit : revenu_median, taux_pauvrete par arrondissement (via code commune)
Compétence validée : C2.3
"""
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR

SRC  = BRONZE_DIR / "revenus_insee_paris.csv"
DEST = SILVER_DIR / "revenus.parquet"

# Paris : code commune = 75101 (1er) à 75120 (20e)
# Arrondissement = code_commune - 75100
CODE_TO_ARR = {75100 + i: i for i in range(1, 21)}


def run():
    logger.info("Silver revenus INSEE Filosofi…")

    if not SRC.exists():
        logger.warning(f"  {SRC.name} absent — skip")
        return False

    encodings = ["utf-8", "latin-1", "cp1252"]
    df = None
    for sep in [";", ","]:
        for enc in encodings:
            try:
                df = pd.read_csv(SRC, sep=sep, encoding=enc, low_memory=False)
                if len(df.columns) > 3:
                    break
            except Exception:
                continue
        if df is not None and len(df.columns) > 3:
            break

    if df is None:
        logger.error("  Impossible de lire le fichier revenus")
        return False

    df.columns = df.columns.str.lower().str.strip()
    logger.info(f"  Colonnes : {list(df.columns[:10])}")

    # Identifie colonne code commune
    code_col = next(
        (c for c in df.columns if c in ["codgeo", "code_commune", "com", "depcom"]),
        None
    )
    if code_col is None:
        logger.error("  Colonne code commune introuvable")
        return False

    df[code_col] = pd.to_numeric(df[code_col], errors="coerce")
    df = df[df[code_col].isin(CODE_TO_ARR.keys())].copy()
    df["arrondissement"] = df[code_col].map(CODE_TO_ARR)

    # Colonnes de revenus (Filosofi : Q2 = médiane)
    col_map = {}
    for pattern, alias in [
        (["q2", "med", "median", "revenu_median"], "revenu_median"),
        (["d1", "decile1", "premier_decile"],       "revenu_d1"),
        (["d9", "decile9", "neuvieme_decile"],       "revenu_d9"),
        (["taux_pauv", "tp", "pauvrete"],            "taux_pauvrete"),
        (["gini"],                                   "gini"),
    ]:
        col = next((c for c in df.columns for p in pattern if p in c), None)
        if col:
            col_map[col] = alias

    df = df.rename(columns=col_map)

    # Nettoyage numériques
    for alias in col_map.values():
        if alias in df.columns:
            df[alias] = pd.to_numeric(
                df[alias].astype(str).str.replace(",", "."), errors="coerce"
            )

    keep_cols = ["arrondissement"] + [a for a in col_map.values() if a in df.columns]
    df_clean = df[keep_cols].dropna(subset=["arrondissement"])
    df_clean["arrondissement"] = df_clean["arrondissement"].astype(int)

    df_clean.to_parquet(DEST, index=False)
    logger.success(f"  ✓ {len(df_clean)} arrondissements → {DEST.name}")
    logger.info(f"  Indicateurs : {[c for c in df_clean.columns if c != 'arrondissement']}")
    return True


if __name__ == "__main__":
    run()
