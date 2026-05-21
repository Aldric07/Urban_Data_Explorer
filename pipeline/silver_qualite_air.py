"""
pipeline/silver_qualite_air.py
Bronze → Silver : Normalise les données qualité de l'air AIRPARIF.
Produit : iqa_moyen, no2, pm25 par arrondissement
Compétence validée : C2.3
"""
import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR

SRC  = BRONZE_DIR / "qualite_air_paris.json"
DEST = SILVER_DIR / "qualite_air.parquet"


def run():
    logger.info("Silver qualité de l'air…")

    if not SRC.exists():
        logger.warning(f"  {SRC.name} absent — skip")
        return False

    raw = json.loads(SRC.read_text())

    rows = []

    # Format données statiques de repli (dict arrondissements)
    if "arrondissements" in raw:
        for arr_str, vals in raw["arrondissements"].items():
            rows.append({
                "arrondissement": int(arr_str),
                "iqa_moyen": vals.get("iqa_moyen"),
                "no2_µg_m3": vals.get("no2_µg_m3"),
                "pm25_µg_m3": vals.get("pm25_µg_m3"),
            })

    # Format API live AIRPARIF (liste de mesures)
    elif isinstance(raw, list):
        for record in raw:
            arr = None
            commune = str(record.get("commune_code", "") or record.get("insee", ""))
            if commune.startswith("751") and len(commune) == 5:
                try:
                    arr = int(commune[-2:].lstrip("0") or "0")
                except ValueError:
                    pass
            if arr:
                rows.append({
                    "arrondissement": arr,
                    "iqa_moyen": record.get("indice") or record.get("iqa"),
                    "no2_µg_m3": record.get("no2"),
                    "pm25_µg_m3": record.get("pm25") or record.get("pm2_5"),
                })

    if not rows:
        logger.error("  Format qualité air non reconnu")
        return False

    df = pd.DataFrame(rows)
    df["arrondissement"] = df["arrondissement"].astype(int)
    df = df.dropna(subset=["arrondissement"])

    # Qualité de l'air : score inverse (moins de pollution = meilleur score)
    # IQA 0-100 : 0 = excellent, 100 = mauvais (norme française)
    if "iqa_moyen" in df.columns:
        df["score_air"] = (100 - df["iqa_moyen"]).clip(0, 100).round(1)

    df.to_parquet(DEST, index=False)
    logger.success(f"  ✓ {len(df)} arrondissements qualité air → {DEST.name}")
    return True


if __name__ == "__main__":
    run()
