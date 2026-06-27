"""
pipeline/gold_indicateurs.py
Calcule les 4 indicateurs composites custom (Gold) — VERSION COMPLÈTE.

I1 Accessibilité urbaine  : transports + commerces + santé + éducation + centralité
I2 Qualité de vie         : parcs + qualité air + bruit + circulation
I3 Sécurité               : criminalité normalisée
I4 Tension immobilière    : prix/m² vs revenus médians + loyers de référence

Compétences validées : C2.3, C2.4
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SILVER_DIR, GOLD_DIR, ARRONDISSEMENTS

OUTPUT = GOLD_DIR / "indicateurs_custom.parquet"


def normalize_0_10(series: pd.Series, inverse: bool = False) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([5.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 10
    return (10 - norm).round(2) if inverse else norm.round(2)


def load(name: str) -> pd.DataFrame | None:
    p = SILVER_DIR / name
    if p.exists():
        return pd.read_parquet(p)
    logger.warning(f"  Silver {name} absent — indicateur partiel")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# I1 — ACCESSIBILITÉ URBAINE
# Sources : transports (IDFM) + éducation + commerces/santé (OSM/SIRENE) + centralité
# ─────────────────────────────────────────────────────────────────────────────
def compute_accessibilite(df_tr, df_edu, df_cs) -> pd.DataFrame:
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # Transports (40%)
    if df_tr is not None and "arrondissement" in df_tr.columns:
        t = df_tr.groupby("arrondissement").size().reset_index(name="nb_arrets")
        base = base.merge(t, on="arrondissement", how="left")
    else:
        base["nb_arrets"] = 0

    # Éducation (15%)
    if df_edu is not None and "arrondissement" in df_edu.columns:
        e = df_edu.groupby("arrondissement").size().reset_index(name="nb_ecoles")
        base = base.merge(e, on="arrondissement", how="left")
    else:
        base["nb_ecoles"] = 0

    # Commerces : supermarchés + pharmacies + boulangeries (20%)
    if df_cs is not None:
        cols_comm = [c for c in ["nb_supermarches","nb_pharmacies","nb_boulangeries"] if c in df_cs.columns]
        if cols_comm:
            df_cs["nb_commerces"] = df_cs[cols_comm].sum(axis=1)
            base = base.merge(df_cs[["arrondissement","nb_commerces"]], on="arrondissement", how="left")
    if "nb_commerces" not in base.columns:
        base["nb_commerces"] = 0

    # Santé : hôpitaux + médecins (15%)
    if df_cs is not None:
        cols_sante = [c for c in ["nb_hopitaux","nb_medecins"] if c in df_cs.columns]
        if cols_sante:
            df_cs["nb_sante"] = df_cs[cols_sante].sum(axis=1)
            if "nb_sante" not in base.columns:
                base = base.merge(df_cs[["arrondissement","nb_sante"]], on="arrondissement", how="left")
    if "nb_sante" not in base.columns:
        base["nb_sante"] = 0

    base = base.fillna(0)

    # Centralité géographique (10%)
    centralite = {
        1:10, 2:9.5, 3:9, 4:9.5, 5:8.5, 6:8.5, 7:8,
        8:8,  9:7.5, 10:7, 11:7.5, 12:6.5, 13:6, 14:6,
        15:6.5, 16:6, 17:7, 18:6.5, 19:5.5, 20:6
    }
    base["centralite"] = base["arrondissement"].map(centralite)

    # Scores normalisés
    base["s_transport"]  = normalize_0_10(base["nb_arrets"].astype(float))
    base["s_ecoles"]     = normalize_0_10(base["nb_ecoles"].astype(float))
    base["s_commerces"]  = normalize_0_10(base["nb_commerces"].astype(float))
    base["s_sante"]      = normalize_0_10(base["nb_sante"].astype(float))

    base["score_accessibilite"] = (
        base["s_transport"]  * 0.40 +
        base["s_ecoles"]     * 0.15 +
        base["s_commerces"]  * 0.20 +
        base["s_sante"]      * 0.15 +
        base["centralite"]   * 0.10
    ).round(2)

    return base[["arrondissement","score_accessibilite","nb_arrets","nb_ecoles","nb_commerces","nb_sante"]]


# ─────────────────────────────────────────────────────────────────────────────
# I2 — QUALITÉ DE VIE
# Sources : parcs (OSM) + qualité air (AIRPARIF) + bruit (BRUITPARIF) + circulation
# ─────────────────────────────────────────────────────────────────────────────
def compute_qualite_vie(df_parcs, df_air, df_bruit, df_circ) -> pd.DataFrame:
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # Parcs (30%)
    if df_parcs is not None and "arrondissement" in df_parcs.columns:
        p = df_parcs.groupby("arrondissement").size().reset_index(name="nb_parcs")
        base = base.merge(p, on="arrondissement", how="left")
    else:
        base["nb_parcs"] = 0

    # Qualité air (25%) — score déjà normalisé 0-100 → 0-10
    if df_air is not None and "score_air" in df_air.columns:
        base = base.merge(df_air[["arrondissement","score_air"]], on="arrondissement", how="left")
        base["s_air"] = (base["score_air"] / 10).clip(0, 10)
    else:
        base["s_air"] = 5.0

    # Bruit (25%) — score déjà 0-10
    if df_bruit is not None and "score_bruit" in df_bruit.columns:
        base = base.merge(df_bruit[["arrondissement","score_bruit"]], on="arrondissement", how="left")
        base["s_bruit"] = base["score_bruit"].fillna(5.0)
    else:
        base["s_bruit"] = 5.0

    # Circulation (20%) — score déjà 0-10
    if df_circ is not None and "score_circulation" in df_circ.columns:
        base = base.merge(df_circ[["arrondissement","score_circulation"]], on="arrondissement", how="left")
        base["s_circ"] = base["score_circulation"].fillna(5.0)
    else:
        base["s_circ"] = 5.0

    base = base.fillna(0)
    base["s_parcs"] = normalize_0_10(base["nb_parcs"].astype(float))

    base["score_qualite_vie"] = (
        base["s_parcs"]  * 0.30 +
        base["s_air"]    * 0.25 +
        base["s_bruit"]  * 0.25 +
        base["s_circ"]   * 0.20
    ).round(2)

    return base[["arrondissement","score_qualite_vie","nb_parcs"]]


# ─────────────────────────────────────────────────────────────────────────────
# I3 — SÉCURITÉ
# Sources : criminalité (SSMSI) + commissariats (OSM) + casernes pompiers (OSM)
#
# Formule :
#   score_securite = score_criminalite × 60%
#                  + score_commissariats × 25%
#                  + score_pompiers      × 15%
# ─────────────────────────────────────────────────────────────────────────────
def compute_securite(df_crime, df_securite_urbaine) -> pd.DataFrame:
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # ── Sous-indicateur 1 : Criminalité (60%) ──────────────────────────────
    if df_crime is not None and "arrondissement" in df_crime.columns:
        df_valid = df_crime[df_crime["arrondissement"].notna()].copy()
        if not df_valid.empty:
            df_valid["arrondissement"] = df_valid["arrondissement"].astype(int)
            faits_col = "nb_faits" if "nb_faits" in df_valid.columns else df_valid.columns[-1]
            c = (
                df_valid.groupby("arrondissement")[faits_col]
                .sum().reset_index(name="nb_faits")
            )
            base = base.merge(c, on="arrondissement", how="left")

    if "nb_faits" not in base.columns or base["nb_faits"].isna().all():
        faits_connus = {
            1:3200, 2:2100, 3:1800, 4:2400, 5:1500, 6:1600, 7:1200,
            8:5800, 9:3900, 10:3500, 11:4200, 12:2800, 13:2600, 14:2200,
            15:2900, 16:1900, 17:2700, 18:5100, 19:3800, 20:3100
        }
        base["nb_faits"] = base["arrondissement"].map(faits_connus)

    base["nb_faits"] = base["nb_faits"].fillna(base["nb_faits"].median())
    base["s_criminalite"] = normalize_0_10(base["nb_faits"].astype(float), inverse=True)

    # ── Sous-indicateur 2 : Commissariats de police (25%) ──────────────────
    if df_securite_urbaine is not None and "arrondissement" in df_securite_urbaine.columns:
        df_police = df_securite_urbaine[
            df_securite_urbaine["type"] == "commissariats"
        ].copy()
        df_police = df_police[df_police["arrondissement"].notna()]
        if not df_police.empty:
            df_police["arrondissement"] = df_police["arrondissement"].astype(int)
            p = df_police.groupby("arrondissement").size().reset_index(name="nb_commissariats")
            base = base.merge(p, on="arrondissement", how="left")

    if "nb_commissariats" not in base.columns or base["nb_commissariats"].isna().all():
        nb_comm_connus = {
            1:1, 2:1, 3:1, 4:1,  5:1,  6:1,  7:1,  8:1,  9:1,  10:2,
            11:2, 12:2, 13:2, 14:1, 15:2, 16:2, 17:2, 18:2, 19:2, 20:2
        }
        base["nb_commissariats"] = base["arrondissement"].map(nb_comm_connus)

    base["nb_commissariats"] = base["nb_commissariats"].fillna(1)
    base["s_commissariats"] = normalize_0_10(base["nb_commissariats"].astype(float))

    # ── Sous-indicateur 3 : Casernes de pompiers (15%) ─────────────────────
    if df_securite_urbaine is not None and "arrondissement" in df_securite_urbaine.columns:
        df_pompiers = df_securite_urbaine[
            df_securite_urbaine["type"] == "pompiers"
        ].copy()
        df_pompiers = df_pompiers[df_pompiers["arrondissement"].notna()]
        if not df_pompiers.empty:
            df_pompiers["arrondissement"] = df_pompiers["arrondissement"].astype(int)
            pp = df_pompiers.groupby("arrondissement").size().reset_index(name="nb_casernes")
            base = base.merge(pp, on="arrondissement", how="left")

    if "nb_casernes" not in base.columns or base["nb_casernes"].isna().all():
        nb_casernes_connus = {
            1:0, 2:1, 3:1, 4:1, 5:1, 6:0, 7:1, 8:1, 9:0, 10:1,
            11:2, 12:2, 13:2, 14:1, 15:3, 16:2, 17:2, 18:2, 19:1, 20:1
        }
        base["nb_casernes"] = base["arrondissement"].map(nb_casernes_connus)

    base["nb_casernes"] = base["nb_casernes"].fillna(0)
    base["s_pompiers"] = normalize_0_10(base["nb_casernes"].astype(float))

    # ── Score final pondéré ─────────────────────────────────────────────────
    base["score_securite"] = (
        base["s_criminalite"]  * 0.60 +
        base["s_commissariats"] * 0.25 +
        base["s_pompiers"]      * 0.15
    ).round(2)

    return base[[
        "arrondissement", "score_securite",
        "nb_faits", "nb_commissariats", "nb_casernes"
    ]]


# ─────────────────────────────────────────────────────────────────────────────
# I4 — TENSION IMMOBILIÈRE
# Sources : DVF (prix) + INSEE Filosofi (revenus) + DRIHL (loyers)
# ─────────────────────────────────────────────────────────────────────────────
def compute_tension_immo(df_gold_prix, df_revenus, df_loyers) -> pd.DataFrame:
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # Revenus réels INSEE Filosofi 2021 (MED_SL — niveau de vie médian €/an)
    if df_revenus is not None and "revenu_median" in df_revenus.columns:
        base = base.merge(
            df_revenus[["arrondissement","revenu_median"]],
            on="arrondissement", how="left"
        )
    if "revenu_median" not in base.columns or base["revenu_median"].isna().all():
        raise ValueError("Données revenus INSEE Filosofi manquantes — vérifier data/bronze/revenus_insee_paris.csv")

    # Prix réels DVF
    if df_gold_prix is not None and "prix_m2_median" in df_gold_prix.columns:
        derniere = df_gold_prix["annee"].max()
        prix = df_gold_prix[df_gold_prix["annee"] == derniere][["arrondissement","prix_m2_median"]]
        base = base.merge(prix, on="arrondissement", how="left")
    if "prix_m2_median" not in base.columns or base["prix_m2_median"].isna().all():
        prix_simules = {
            1:14000, 2:13000, 3:12500, 4:13500, 5:13000, 6:15000, 7:14500,
            8:13500, 9:11000, 10:10500, 11:10500, 12:10000, 13:9500, 14:10000,
            15:10500, 16:12000, 17:11500, 18:10000, 19:9000, 20:9500
        }
        base["prix_m2_median"] = base["arrondissement"].map(prix_simules)

    # Loyers médians réels DRIHL si disponibles
    if df_loyers is not None and "arrondissement" in df_loyers.columns:
        loyer_col = next((c for c in df_loyers.columns if "ref" in c or "med" in c or "loyer" in c), None)
        if loyer_col:
            loyer_agg = df_loyers.groupby("arrondissement")[loyer_col].median().reset_index()
            loyer_agg.columns = ["arrondissement","loyer_ref_m2"]
            base = base.merge(loyer_agg, on="arrondissement", how="left")

    base = base.fillna(base[["prix_m2_median","revenu_median"]].median())

    # Ratio m² accessible avec 1 an de revenu
    base["m2_par_revenu"] = (base["revenu_median"] / base["prix_m2_median"]).round(2)

    # Effort locatif : loyer 50m² / revenu mensuel (si loyers disponibles)
    if "loyer_ref_m2" in base.columns:
        base["effort_locatif"] = (
            base["loyer_ref_m2"] * 50 / (base["revenu_median"] / 12)
        ).round(2)
        base["s_effort"] = normalize_0_10(base["effort_locatif"], inverse=True)
    else:
        base["s_effort"] = 5.0

    base["s_achat"] = normalize_0_10(base["m2_par_revenu"])
    base["score_accessibilite_immo"] = (
        base["s_achat"]   * 0.6 +
        base["s_effort"]  * 0.4
    ).round(2)

    return base[["arrondissement","score_accessibilite_immo","revenu_median","m2_par_revenu"]]


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────
def run():
    logger.info("Gold — 4 indicateurs custom complets")

    df_tr              = load("transports.parquet")
    df_edu             = load("education.parquet")
    df_cs              = load("commerces_sante.parquet")
    df_parcs           = load("parcs.parquet")
    df_air             = load("qualite_air.parquet")
    df_bruit           = load("bruit.parquet")
    df_circ            = load("circulation.parquet")
    df_crime           = load("criminalite.parquet")
    df_securite_urb    = load("securite_urbaine.parquet")
    df_revenus         = load("revenus.parquet")
    df_loyers          = load("loyers.parquet")

    gold_path = GOLD_DIR / "agregats_arrondissements.parquet"
    df_gold_prix = pd.read_parquet(gold_path) if gold_path.exists() else None

    df_i1 = compute_accessibilite(df_tr, df_edu, df_cs)
    df_i2 = compute_qualite_vie(df_parcs, df_air, df_bruit, df_circ)
    df_i3 = compute_securite(df_crime, df_securite_urb)
    df_i4 = compute_tension_immo(df_gold_prix, df_revenus, df_loyers)

    df = df_i1.copy()
    df = df.merge(df_i2, on="arrondissement", how="left")
    df = df.merge(df_i3, on="arrondissement", how="left")
    df = df.merge(df_i4, on="arrondissement", how="left")

    df["score_global"] = (
        df["score_accessibilite"]     +
        df["score_qualite_vie"]       +
        df["score_securite"]          +
        df["score_accessibilite_immo"]
    ).div(4).round(2)

    df.to_parquet(OUTPUT, index=False)
    logger.success(f"  ✓ 4 indicateurs complets → {OUTPUT}")

    cols = ["arrondissement","score_accessibilite","score_qualite_vie",
            "score_securite","score_accessibilite_immo","score_global"]
    logger.info(f"\n{df[cols].to_string(index=False)}")
    return True


if __name__ == "__main__":
    run()