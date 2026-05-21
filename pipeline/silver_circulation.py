"""
pipeline/silver_circulation.py
Bronze → Silver : Normalise les données de trafic routier Paris.
Fix : gestion correcte des colonnes selon le format reçu (live vs statique).
"""
import json, sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, ARRONDISSEMENTS

SRC  = BRONZE_DIR / "circulation_paris.json"
DEST = SILVER_DIR / "circulation.parquet"


def normalize_0_10(series: pd.Series, inverse: bool = False) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([5.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 10
    return (10 - norm).round(2) if inverse else norm.round(2)


def run():
    logger.info("Silver circulation (trafic Paris)…")

    if not SRC.exists():
        logger.warning(f"  {SRC.name} absent — skip")
        return False

    raw = json.loads(SRC.read_text())
    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # ── Format statique (dict arrondissements) ────────────────────────────
    if "arrondissements" in raw:
        rows = []
        for arr_str, vals in raw["arrondissements"].items():
            rows.append({
                "arrondissement":    int(arr_str),
                "tmja_moyen":        vals.get("tmja_moyen"),
                "score_circulation": vals.get("score_circulation"),
            })
        df = pd.DataFrame(rows)
        base = base.merge(df, on="arrondissement", how="left")

    # ── Format Paris Open Data live (liste de capteurs) ───────────────────
    elif "records" in raw or isinstance(raw.get("source"), str):
        records = raw.get("records", [])
        if records:
            # Essai d'extraction arrondissement depuis les champs disponibles
            rows = []
            for rec in records:
                arr = None
                for field in ["arrondissement", "arr", "code_arr", "codearr"]:
                    val = rec.get(field)
                    if val:
                        try:
                            arr = int(str(val).strip().lstrip("0") or "0")
                            break
                        except ValueError:
                            pass
                debit = rec.get("q") or rec.get("debit") or rec.get("tmja") or rec.get("debit_moyen_journalier")
                if arr and debit:
                    rows.append({"arrondissement": arr, "tmja_live": float(debit)})

            if rows:
                df_live = pd.DataFrame(rows)
                df_live = df_live[df_live["arrondissement"].between(1, 20)]
                df_agg = df_live.groupby("arrondissement")["tmja_live"].mean().reset_index()
                df_agg.columns = ["arrondissement", "tmja_moyen"]
                base = base.merge(df_agg, on="arrondissement", how="left")
            else:
                logger.info("  Capteurs live sans arrondissement — score par défaut")
                base["tmja_moyen"] = None

    # ── Calcul score_circulation ──────────────────────────────────────────
    if "score_circulation" not in base.columns or base["score_circulation"].isna().all():
        if "tmja_moyen" in base.columns and base["tmja_moyen"].notna().any():
            base["score_circulation"] = normalize_0_10(
                base["tmja_moyen"].fillna(base["tmja_moyen"].median()),
                inverse=True
            )
        else:
            # Score par défaut basé sur les patterns connus Paris
            scores_defaut = {
                1: 2.8, 2: 2.2, 3: 3.5, 4: 3.2, 5: 4.2, 6: 4.0,
                7: 5.0, 8: 1.2, 9: 1.8, 10: 2.1, 11: 3.0, 12: 3.8,
                13: 3.5, 14: 4.0, 15: 3.0, 16: 4.5, 17: 2.8, 18: 3.2,
                19: 4.0, 20: 4.2
            }
            base["score_circulation"] = base["arrondissement"].map(scores_defaut)

    # S'assurer que tmja_moyen existe toujours (même vide)
    if "tmja_moyen" not in base.columns:
        base["tmja_moyen"] = None

    base["score_circulation"] = base["score_circulation"].fillna(5.0).round(2)

    # Colonnes finales
    keep = ["arrondissement", "score_circulation"]
    if base["tmja_moyen"].notna().any():
        keep.append("tmja_moyen")

    base[keep].to_parquet(DEST, index=False)
    logger.success(f"  ✓ Circulation Silver : {len(base)} arrondissements → {DEST.name}")
    return True


if __name__ == "__main__":
    run()