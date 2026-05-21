"""
pipeline/gold_agregats.py
Silver → Gold : Calcule les agrégats par arrondissement et par année.
Produit le fichier principal utilisé par l'API et le dashboard.
Compétences validées : C2.3, C2.4, C1.3
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SILVER_DIR, GOLD_DIR, ARRONDISSEMENTS, DVF_YEARS

SILVER_DVF = SILVER_DIR / "dvf"
OUTPUT     = GOLD_DIR / "agregats_arrondissements.parquet"


def load_silver_dvf() -> pd.DataFrame | None:
    src = SILVER_DVF / "dvf_all.parquet"
    if not src.exists():
        # Essaie de charger les fichiers par année
        frames = []
        for year in DVF_YEARS:
            f = SILVER_DVF / f"dvf_{year}.parquet"
            if f.exists():
                frames.append(pd.read_parquet(f))
        if frames:
            return pd.concat(frames, ignore_index=True)
        logger.error("  Aucune donnée DVF Silver trouvée. Lance d'abord silver_dvf.py")
        return None
    return pd.read_parquet(src)


def load_silver_logements_sociaux() -> pd.DataFrame | None:
    src = SILVER_DIR / "logements_sociaux.parquet"
    if not src.exists():
        logger.warning("  Logements sociaux Silver absent — indicateur ignoré")
        return None
    return pd.read_parquet(src)


def aggregate_dvf(df: pd.DataFrame) -> pd.DataFrame:
    """Agrégats DVF : prix médian, volume, distribution par type."""
    agg = (
        df.groupby(["arrondissement", "annee"])
        .agg(
            prix_m2_median=("prix_m2", "median"),
            prix_m2_moyen=("prix_m2", "mean"),
            nb_transactions=("prix_m2", "count"),
            surface_mediane=("surface_reelle_bati", "median"),
        )
        .reset_index()
    )

    # Distribution par type de local
    type_dist = (
        df.groupby(["arrondissement", "annee", "type_local"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    type_dist.columns.name = None
    for col in ["Appartement", "Maison"]:
        if col not in type_dist.columns:
            type_dist[col] = 0

    agg = agg.merge(type_dist, on=["arrondissement", "annee"], how="left")
    agg["prix_m2_median"] = agg["prix_m2_median"].round(0)
    agg["prix_m2_moyen"]  = agg["prix_m2_moyen"].round(0)
    return agg


def compute_variation(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule la variation du prix/m² par rapport à l'année précédente."""
    df = df.sort_values(["arrondissement", "annee"])
    df["prix_m2_variation_pct"] = (
        df.groupby("arrondissement")["prix_m2_median"]
        .pct_change() * 100
    ).round(1)
    return df


def aggregate_logements_sociaux(df_rpls: pd.DataFrame) -> pd.DataFrame | None:
    """Part des logements sociaux par arrondissement."""
    if df_rpls is None:
        return None
    try:
        agg = (
            df_rpls.groupby(["arrondissement", "annee"])
            .agg(nb_logements_sociaux=("id", "count"))
            .reset_index()
        )
        return agg
    except Exception as e:
        logger.warning(f"  Agrégation logements sociaux échouée : {e}")
        return None


def run():
    logger.info("Gold — agrégats par arrondissement")

    df_dvf = load_silver_dvf()
    if df_dvf is None:
        return False

    logger.info(f"  DVF chargé : {len(df_dvf):,} lignes")

    # Agrégats principaux
    df_gold = aggregate_dvf(df_dvf)
    df_gold = compute_variation(df_gold)

    # Fusion logements sociaux si disponible
    df_rpls = load_silver_logements_sociaux()
    if df_rpls is not None:
        df_ls = aggregate_logements_sociaux(df_rpls)
        if df_ls is not None:
            df_gold = df_gold.merge(df_ls, on=["arrondissement", "annee"], how="left")

    # Vérifie couverture arrondissements
    arr_couverts = sorted(df_gold["arrondissement"].unique())
    logger.info(f"  Arrondissements couverts : {arr_couverts}")
    if len(arr_couverts) < 20:
        manquants = set(ARRONDISSEMENTS) - set(arr_couverts)
        logger.warning(f"  Arrondissements manquants : {sorted(manquants)}")

    df_gold.to_parquet(OUTPUT, index=False)
    logger.success(f"  ✓ Gold agrégats : {len(df_gold):,} lignes → {OUTPUT}")
    logger.info(f"  Colonnes : {list(df_gold.columns)}")
    return True


if __name__ == "__main__":
    run()
