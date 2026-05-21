"""
pipeline/silver_loyers.py
Bronze → Silver : Nettoyage des loyers de référence (encadrement DRIHL).
Produit : loyer_ref par arrondissement, type logement, nb pièces
Compétence validée : C2.3
"""
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR

SRC  = BRONZE_DIR / "loyers_reference_paris.csv"
DEST = SILVER_DIR / "loyers.parquet"


def run():
    logger.info("Silver loyers de référence…")

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
        logger.error("  Impossible de lire le fichier loyers")
        return False

    df.columns = df.columns.str.lower().str.strip().str.replace(r"[\s/]", "_", regex=True)
    logger.info(f"  Colonnes : {list(df.columns)}")

    # Mapping colonnes flexibles
    col_map = {}
    for pattern, alias in [
        (["arr", "arrondissement"],      "arrondissement"),
        (["piece", "nb_pieces", "npi"],  "nb_pieces"),
        (["ref_majore", "loyer_max", "plafond"], "loyer_max_m2"),
        (["ref_minoree", "loyer_min", "plancher"], "loyer_min_m2"),
        (["reference", "loyer_ref", "loyer_med"], "loyer_ref_m2"),
        (["epoque", "periode", "construction"], "epoque_construction"),
        (["meuble", "type_loc"], "meuble"),
    ]:
        col = next((c for c in df.columns for p in pattern if p in c), None)
        if col:
            col_map[col] = alias

    df = df.rename(columns=col_map)

    # Nettoyage arrondissement
    if "arrondissement" in df.columns:
        df["arrondissement"] = pd.to_numeric(
            df["arrondissement"].astype(str).str.extract(r"(\d+)")[0],
            errors="coerce"
        )
        df = df[df["arrondissement"].between(1, 20)]
        df["arrondissement"] = df["arrondissement"].astype(int)

    # Nettoyage loyers
    for col in ["loyer_max_m2", "loyer_min_m2", "loyer_ref_m2"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ".").str.extract(r"([\d.]+)")[0],
                errors="coerce"
            )

    df.to_parquet(DEST, index=False)
    logger.success(f"  ✓ {len(df):,} lignes loyers → {DEST.name}")
    return True


if __name__ == "__main__":
    run()
