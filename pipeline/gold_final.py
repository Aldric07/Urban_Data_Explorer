"""
pipeline/gold_final.py
Consolidation finale Silver → Gold.
Fix logements sociaux : merge sur arrondissement uniquement (pas d'année),
et calcul du pourcentage depuis les données RPLS réelles.
"""
import sys
from pathlib import Path
import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SILVER_DIR, GOLD_DIR

OUTPUT = GOLD_DIR / "gold_final.parquet"


def load_silver(name):
    p = SILVER_DIR / name
    if p.exists():
        return pd.read_parquet(p)
    logger.warning(f"  Silver {name} absent")
    return None


def load_gold(name):
    p = GOLD_DIR / name
    if p.exists():
        return pd.read_parquet(p)
    logger.warning(f"  Gold {name} absent")
    return None


def run():
    logger.info("Gold final — consolidation complète")

    # ── Base : agrégats DVF (80 lignes : 20 arr × 4 années) ───────────────
    df = load_gold("agregats_arrondissements.parquet")
    if df is None:
        logger.error("  Agrégats DVF manquants — lance gold_agregats.py d'abord")
        return False

    # Supprime nb_logements_sociaux déjà présent dans agregats (issu du merge RPLS)
    # pour éviter les doublons _x/_y
    df = df.drop(columns=["nb_logements_sociaux"], errors="ignore")

    # ── Logements sociaux (RPLS) ───────────────────────────────────────────
    # Le Silver RPLS a 1 ligne par arrondissement (données 2022)
    # On le merge sur arrondissement UNIQUEMENT → valeur identique pour toutes les années
    df_ls = load_silver("logements_sociaux.parquet")
    if df_ls is not None:
        logger.info(f"  RPLS Silver colonnes : {list(df_ls.columns)}")

        # Construit un agrégat propre par arrondissement
        ls_cols = ["arrondissement"]
        if "nb_logements_sociaux" in df_ls.columns:
            ls_cols.append("nb_logements_sociaux")
        # Cherche les deux noms possibles selon la transformation Silver
        if "part_logements_sociaux_pct" in df_ls.columns:
            ls_cols.append("part_logements_sociaux_pct")
        elif "part_ls_pct" in df_ls.columns:
            ls_cols.append("part_ls_pct")

        df_ls_clean = df_ls[ls_cols].drop_duplicates("arrondissement").copy()
        df_ls_clean = df_ls_clean.rename(columns={"part_ls_pct": "part_logements_sociaux_pct"})

        df = df.merge(df_ls_clean, on="arrondissement", how="left")
        ls_present = "nb_logements_sociaux" in df.columns or "part_logements_sociaux_pct" in df.columns
        logger.info(f"  Logements sociaux fusionnés : {ls_present}")

    # ── Revenus INSEE ──────────────────────────────────────────────────────
    df_rev = load_silver("revenus.parquet")
    if df_rev is not None:
        rev_cols = ["arrondissement"] + [
            c for c in df_rev.columns
            if c in ["revenu_median", "taux_pauvrete", "revenu_d1", "revenu_d9", "gini"]
        ]
        df = df.merge(df_rev[rev_cols].drop_duplicates("arrondissement"),
                      on="arrondissement", how="left")

    # ── Tension immobilière (prix réels / revenus réels) ───────────────────
    if "revenu_median" in df.columns and "prix_m2_median" in df.columns:
        df["m2_par_revenu_annuel"] = (
            df["revenu_median"] / df["prix_m2_median"]
        ).round(2)
        df["annees_pour_50m2"] = (
            (df["prix_m2_median"] * 50) / df["revenu_median"]
        ).round(1)

    # ── Loyers DRIHL ──────────────────────────────────────────────────────
    df_loyers = load_silver("loyers.parquet")
    if df_loyers is not None and "arrondissement" in df_loyers.columns:
        loyer_col = next(
            (c for c in df_loyers.columns
             if "référence" in c.lower() and "major" not in c.lower() and "minor" not in c.lower()),
            None
        )
        if loyer_col:
            df_lagg = (
                df_loyers.groupby("arrondissement")[loyer_col]
                .median().reset_index()
                .rename(columns={loyer_col: "loyer_ref_median_m2"})
            )
            df = df.merge(df_lagg, on="arrondissement", how="left")

    # ── Qualité de l'air ───────────────────────────────────────────────────
    df_air = load_silver("qualite_air.parquet")
    if df_air is not None:
        air_cols = ["arrondissement"] + [
            c for c in df_air.columns
            if c in ["iqa_moyen", "no2_µg_m3", "pm25_µg_m3", "score_air"]
        ]
        df = df.merge(df_air[air_cols].drop_duplicates("arrondissement"),
                      on="arrondissement", how="left")

    # ── Indicateurs custom ─────────────────────────────────────────────────
    df_ind = load_gold("indicateurs_custom.parquet")
    if df_ind is not None:
        ind_cols = ["arrondissement"] + [
            c for c in df_ind.columns
            if c.startswith("score_") or c in ["nb_arrets","nb_ecoles","nb_parcs","nb_faits"]
        ]
        # Ne fusionne que les colonnes pas encore présentes
        new_cols = [c for c in ind_cols if c not in df.columns or c == "arrondissement"]
        df = df.merge(df_ind[new_cols].drop_duplicates("arrondissement"),
                      on="arrondissement", how="left")

    # ── Nettoyage colonnes dupliquées _x/_y ────────────────────────────────
    for col in list(df.columns):
        if col.endswith("_x"):
            base = col[:-2]
            col_y = base + "_y"
            if col_y in df.columns:
                # Fusionne : garde _x si non-nul, sinon _y
                df[base] = df[col].combine_first(df[col_y])
                df = df.drop(columns=[col, col_y])

    df = df.sort_values(["arrondissement", "annee"])
    df.to_parquet(OUTPUT, index=False)

    logger.success(f"  ✓ Gold final : {len(df):,} lignes, {len(df.columns)} colonnes → {OUTPUT.name}")
    logger.info(f"  Colonnes : {list(df.columns)}")

    # Aperçu logements sociaux
    if "part_logements_sociaux_pct" in df.columns:
        derniere = df["annee"].max()
        apercu = df[df["annee"] == derniere][
            ["arrondissement","prix_m2_median","part_logements_sociaux_pct","nb_logements_sociaux"]
        ]
        logger.info(f"\n  Logements sociaux par arrondissement :\n{apercu.to_string(index=False)}")

    return True


if __name__ == "__main__":
    run()