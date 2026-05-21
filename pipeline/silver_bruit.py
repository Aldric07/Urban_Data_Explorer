"""
pipeline/silver_bruit.py
Bronze → Silver : Normalise les données de bruit BRUITPARIF.
Produit : lden_moyen, lnight, score_bruit (0-10) par arrondissement.
Compétence validée : C2.3
"""
import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, ARRONDISSEMENTS

SRC  = BRONZE_DIR / "bruit_paris.json"
DEST = SILVER_DIR / "bruit.parquet"


def normalize_0_10(series: pd.Series, inverse: bool = False) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([5.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 10
    return (10 - norm) if inverse else norm


def run():
    logger.info("Silver bruit (BRUITPARIF)…")

    if not SRC.exists():
        logger.warning(f"  {SRC.name} absent — skip")
        return False

    raw = json.loads(SRC.read_text())
    rows = []

    # Format statique (dict arrondissements)
    if "arrondissements" in raw:
        for arr_str, vals in raw["arrondissements"].items():
            rows.append({
                "arrondissement": int(arr_str),
                "lden_moyen":     vals.get("lden_moyen"),
                "lnight":         vals.get("lnight"),
                "score_bruit_raw": vals.get("score_bruit"),
            })

    # Format API live BRUITPARIF (records Opendatasoft)
    elif "records" in raw:
        for rec in raw["records"]:
            fields = rec.get("fields", {})
            commune = str(fields.get("commune_code", "") or "")
            if not commune.startswith("751"):
                continue
            try:
                arr = int(commune[-2:].lstrip("0") or "0")
            except ValueError:
                continue
            rows.append({
                "arrondissement": arr,
                "lden_moyen":     fields.get("lden") or fields.get("laeq"),
                "lnight":         fields.get("lnight") or fields.get("ln"),
                "score_bruit_raw": None,
            })

    if not rows:
        logger.error("  Format bruit non reconnu")
        return False

    df = pd.DataFrame(rows)
    df["arrondissement"] = df["arrondissement"].astype(int)
    df = df.dropna(subset=["arrondissement"])

    # Agrégation si plusieurs lignes par arrondissement
    df = (
        df.groupby("arrondissement")
        .agg(
            lden_moyen=("lden_moyen", "mean"),
            lnight=("lnight", "mean"),
            score_bruit_raw=("score_bruit_raw", "mean"),
        )
        .reset_index()
    )

    # Score bruit 0-10 : Lden élevé = mauvais → inverse
    if df["lden_moyen"].notna().any():
        df["score_bruit"] = normalize_0_10(
            df["lden_moyen"].fillna(df["lden_moyen"].mean()),
            inverse=True
        ).round(2)
    elif df["score_bruit_raw"].notna().any():
        df["score_bruit"] = df["score_bruit_raw"].fillna(5.0)
    else:
        df["score_bruit"] = 5.0

    # Couverture complète des 20 arrondissements
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})
    df = base.merge(df, on="arrondissement", how="left")
    df["score_bruit"] = df["score_bruit"].fillna(5.0)

    df.to_parquet(DEST, index=False)
    logger.success(f"  ✓ Bruit Silver : {len(df)} arrondissements → {DEST.name}")
    return True


if __name__ == "__main__":
    run()
