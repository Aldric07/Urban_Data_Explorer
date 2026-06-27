"""
pipeline/silver_dvf.py
Bronze → Silver : Nettoyage et normalisation des données DVF.
- Filtre Paris (75XXX), garde uniquement les appartements et maisons
- Calcule le prix/m²
- Extrait l'arrondissement (code postal 750XX → arrondissement XX)
- Sauvegarde en Parquet partitionné par année
Compétences validées : C2.3, C2.4
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, DVF_YEARS

SILVER_DVF = SILVER_DIR / "dvf"
SILVER_DVF.mkdir(exist_ok=True)


def extract_arrondissement(code_postal: pd.Series) -> pd.Series:
    """75001 → 1, 75020 → 20"""
    cp = code_postal.astype(str)
    arr = cp.str[-2:].str.lstrip("0")
    return pd.to_numeric(arr, errors="coerce")


def process_year(year: int) -> pd.DataFrame | None:
    src = BRONZE_DIR / "dvf" / f"dvf_75_{year}.csv.gz"
    if not src.exists():
        logger.warning(f"  {src.name} absent, skip")
        return None

    logger.info(f"  Traitement DVF {year}…")

    df = pd.read_csv(
        src,
        compression="gzip",
        usecols=[
            "date_mutation", "nature_mutation", "valeur_fonciere",
            "code_postal", "type_local", "surface_reelle_bati",
            "nombre_pieces_principales", "longitude", "latitude"
        ],
        dtype={"code_postal": str},
        low_memory=False,
    )

    # Filtre Paris uniquement
    df = df[df["code_postal"].str.startswith("750", na=False)].copy()

    # Filtre ventes d'appartements et maisons uniquement
    df = df[
        (df["nature_mutation"] == "Vente") &
        (df["type_local"].isin(["Appartement", "Maison"]))
    ].copy()

    # Nettoyage
    df["valeur_fonciere"] = pd.to_numeric(
        df["valeur_fonciere"].astype(str).str.replace(",", "."), errors="coerce"
    )
    df["surface_reelle_bati"] = pd.to_numeric(df["surface_reelle_bati"], errors="coerce")
    df = df.dropna(subset=["valeur_fonciere", "surface_reelle_bati"])
    df = df[df["surface_reelle_bati"] > 5]   # Filtre surfaces aberrantes
    df = df[df["valeur_fonciere"] > 1000]

    # Prix au m²
    df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
    df = df[df["prix_m2"].between(1000, 50000)]  # Filtre valeurs aberrantes

    # Arrondissement
    df["arrondissement"] = extract_arrondissement(df["code_postal"])
    df = df.dropna(subset=["arrondissement"])
    df["arrondissement"] = df["arrondissement"].astype(int)

    # Année
    df["annee"] = year
    df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")

    # Colonnes finales
    df = df[[
        "date_mutation", "annee", "arrondissement", "type_local",
        "valeur_fonciere", "surface_reelle_bati", "prix_m2",
        "nombre_pieces_principales", "longitude", "latitude"
    ]]

    logger.success(f"    {len(df):,} transactions conservées")
    return df


def run():
    logger.info("Silver DVF — nettoyage prix immobiliers")
    frames = []
    for year in DVF_YEARS:
        df = process_year(year)
        if df is not None:
            dest = SILVER_DVF / f"dvf_{year}.parquet"
            df.to_parquet(dest, index=False)
            frames.append(df)
            logger.info(f"    → {dest.name}")

    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        all_dest = SILVER_DVF / "dvf_all.parquet"
        all_df.to_parquet(all_dest, index=False)
        logger.success(f"  ✓ DVF Silver : {len(all_df):,} lignes totales → {all_dest}")
    return len(frames) > 0


if __name__ == "__main__":
    run()
