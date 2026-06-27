"""
pipeline/batch_processor.py — Urban Data Explorer
Pipeline BATCH DVF : retraite les fichiers Bronze, recalcule les agrégats
Gold par arrondissement × année et met à jour PostgreSQL.

Modes d'exécution :
    python3 pipeline/batch_processor.py              # exécution immédiate
    python3 pipeline/batch_processor.py --schedule   # daemon APScheduler (02h00/nuit)
    python3 pipeline/batch_processor.py --dry-run    # analyse sans écriture PostgreSQL

Compétences RNCP40875 validées :
    C2.2 — traitement batch planifiable avec scheduler
    C1.1 — mise à jour PostgreSQL (UPSERT idempotent)
    C2.3 — transformation Bronze → Silver → Gold
    C2.4 — logs structurés horodatés, rapport JSON
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import GOLD_DIR, SILVER_DIR, BRONZE_DIR, DVF_YEARS

REPORTS_DIR = GOLD_DIR / "batch_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

LAST_REPORT_PATH = REPORTS_DIR / "last_report.json"


# ── Détection d'anomalies ─────────────────────────────────────────────────────

def detect_anomalies(df: pd.DataFrame) -> list[dict]:
    """Analyse le Gold final et retourne les anomalies détectées."""
    anomalies: list[dict] = []

    # 1. Arrondissements manquants par année
    for year in sorted(df["annee"].unique()):
        sub = df[df["annee"] == year]
        covered = set(int(a) for a in sub["arrondissement"].unique())
        missing = set(range(1, 21)) - covered
        if missing:
            anomalies.append({
                "type": "arrondissement_manquant",
                "severity": "warning",
                "detail": f"Année {year} : arrondissements absents {sorted(missing)}",
            })

    # 2. Prix aberrants (> 3σ par rapport à la distribution Paris entier)
    if "prix_m2_median" in df.columns:
        prix = df["prix_m2_median"].dropna()
        if len(prix) >= 5:
            mean_p, std_p = float(prix.mean()), float(prix.std())
            seuil_haut = mean_p + 3 * std_p
            seuil_bas  = mean_p - 3 * std_p
            outliers = df[
                (df["prix_m2_median"].notna()) &
                ((df["prix_m2_median"] > seuil_haut) |
                 (df["prix_m2_median"] < max(seuil_bas, 0)))
            ]
            for _, row in outliers.iterrows():
                anomalies.append({
                    "type": "prix_aberrant",
                    "severity": "error" if row["prix_m2_median"] <= 0 else "warning",
                    "detail": (
                        f"Arr.{int(row['arrondissement'])} {int(row['annee'])} : "
                        f"prix_m2_median={row['prix_m2_median']:.0f} "
                        f"(μ={mean_p:.0f}, seuil 3σ={seuil_haut:.0f})"
                    ),
                })

    # 3. Valeurs manquantes dans les colonnes critiques
    for col in ("prix_m2_median", "nb_transactions"):
        if col in df.columns:
            n_nan = int(df[col].isna().sum())
            if n_nan > 0:
                anomalies.append({
                    "type": "valeur_manquante",
                    "severity": "warning",
                    "detail": f"{n_nan} valeur(s) NaN dans la colonne « {col} »",
                })

    # 4. Volume de transactions anormalement faible (< 10 pour un arrondissement/année)
    if "nb_transactions" in df.columns:
        low_tx = df[(df["nb_transactions"].notna()) & (df["nb_transactions"] < 10)]
        for _, row in low_tx.iterrows():
            anomalies.append({
                "type": "volume_faible",
                "severity": "info",
                "detail": (
                    f"Arr.{int(row['arrondissement'])} {int(row['annee'])} : "
                    f"seulement {int(row['nb_transactions'])} transactions"
                ),
            })

    return anomalies


# ── Statistiques du Gold ──────────────────────────────────────────────────────

def collect_stats() -> dict:
    """Collecte les métriques clés du Data Lake après recalcul."""
    stats: dict = {
        "dvf_bronze_files": 0,
        "dvf_silver_files": 0,
        "gold_rows": 0,
        "arrondissements_covered": 0,
        "years_covered": [],
        "nb_transactions_total": 0,
        "prix_m2_median_paris": None,
    }

    dvf_bronze = BRONZE_DIR / "dvf"
    if dvf_bronze.exists():
        stats["dvf_bronze_files"] = len(list(dvf_bronze.glob("*.csv.gz")))

    dvf_silver = SILVER_DIR / "dvf"
    if dvf_silver.exists():
        stats["dvf_silver_files"] = len(
            [f for f in dvf_silver.glob("*.parquet") if f.name != "dvf_all.parquet"]
        )

    gold_path = GOLD_DIR / "gold_final.parquet"
    if gold_path.exists():
        df = pd.read_parquet(gold_path)
        stats["gold_rows"] = len(df)
        if "arrondissement" in df.columns:
            stats["arrondissements_covered"] = int(df["arrondissement"].nunique())
        if "annee" in df.columns:
            stats["years_covered"] = sorted(int(y) for y in df["annee"].unique())
        if "nb_transactions" in df.columns:
            stats["nb_transactions_total"] = int(df["nb_transactions"].sum())
        if "prix_m2_median" in df.columns:
            median_val = df["prix_m2_median"].median()
            stats["prix_m2_median_paris"] = round(float(median_val), 0)

    return stats


# ── Cœur du pipeline batch ────────────────────────────────────────────────────

def run_batch(dry_run: bool = False) -> dict:
    """
    Exécute le pipeline batch complet Bronze → Silver → Gold → PostgreSQL.
    Retourne le dictionnaire rapport.
    """
    batch_id  = datetime.now().strftime("%Y%m%d_%H%M%S")
    t0        = time.time()
    start_iso = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 62)
    logger.info("  BATCH PROCESSOR — Urban Data Explorer")
    logger.info(f"  ID       : {batch_id}")
    mode_str = "DRY-RUN (pas d'écriture PG)" if dry_run else "PRODUCTION"
    logger.info(f"  Mode     : {mode_str}")
    logger.info(f"  Début    : {start_iso}")
    logger.info(f"  DVF_YEARS: {DVF_YEARS}")
    logger.info("=" * 62)

    # ── Imports tardifs (évite les imports circulaires au module-level) ───────
    from pipeline.silver_dvf               import run as run_silver_dvf
    from pipeline.silver_logements_sociaux import run as run_silver_ls
    from pipeline.silver_loyers            import run as run_silver_loyers
    from pipeline.silver_revenus           import run as run_silver_revenus
    from pipeline.silver_qualite_air       import run as run_silver_air
    from pipeline.silver_sources           import run as run_silver_sources
    from pipeline.silver_bruit             import run as run_silver_bruit
    from pipeline.silver_circulation       import run as run_silver_circ
    from pipeline.silver_geo_join          import run as run_geo_join
    from pipeline.gold_agregats            import run as run_gold_agregats
    from pipeline.gold_indicateurs         import run as run_gold_indicateurs
    from pipeline.gold_final               import run as run_gold_final

    PIPELINE_STEPS = [
        # ── Silver ────────────────────────────────────────────────────────
        ("silver_dvf",           "Bronze DVF → Silver normalisé",       run_silver_dvf),
        ("silver_logements",     "Bronze RPLS → Silver logements soc.", run_silver_ls),
        ("silver_loyers",        "Bronze loyers → Silver loyers ref.",  run_silver_loyers),
        ("silver_revenus",       "Bronze INSEE → Silver revenus",        run_silver_revenus),
        ("silver_qualite_air",   "Bronze AIRPARIF → Silver IQA",        run_silver_air),
        ("silver_sources",       "Bronze OSM/IDFM/édu → Silver sources", run_silver_sources),
        ("silver_bruit",         "Bronze BRUITPARIF → Silver bruit",    run_silver_bruit),
        ("silver_circulation",   "Bronze circulation → Silver trafic",  run_silver_circ),
        ("silver_geo_join",      "Jointure coordonnées → arrondissement", run_geo_join),
        # ── Gold ──────────────────────────────────────────────────────────
        ("gold_agregats",        "Silver DVF → Gold agrégats (arr×an)", run_gold_agregats),
        ("gold_indicateurs",     "Silver → Gold 4 indicateurs custom",  run_gold_indicateurs),
        ("gold_final",           "Gold agrégats + indicateurs → final", run_gold_final),
    ]

    steps_results: dict = {}

    for step_key, step_label, fn in PIPELINE_STEPS:
        logger.info(f"\n▶ {step_label}")
        t_step = time.time()
        try:
            ok = fn()
            elapsed = time.time() - t_step
            steps_results[step_key] = {
                "label":      step_label,
                "status":     "ok" if ok else "partial",
                "duration_s": round(elapsed, 2),
            }
            icon = "✓" if ok else "⚠ partiel"
            logger.info(f"  {icon}  ({elapsed:.1f}s)")
        except Exception as exc:
            elapsed = time.time() - t_step
            logger.error(f"  ✗ ERREUR : {exc}")
            steps_results[step_key] = {
                "label":      step_label,
                "status":     "error",
                "error":      str(exc),
                "duration_s": round(elapsed, 2),
            }

    # ── Détection d'anomalies sur Gold final ──────────────────────────────
    logger.info("\n▶ Détection d'anomalies dans gold_final.parquet")
    anomalies: list[dict] = []
    gold_path = GOLD_DIR / "gold_final.parquet"
    if gold_path.exists():
        try:
            df_gold = pd.read_parquet(gold_path)
            anomalies = detect_anomalies(df_gold)
            if anomalies:
                for a in anomalies:
                    fn_log = logger.warning if a["severity"] in ("warning", "info") else logger.error
                    fn_log(f"  [{a['severity'].upper()}] [{a['type']}] {a['detail']}")
            else:
                logger.success("  ✓ Aucune anomalie détectée")
        except Exception as exc:
            logger.error(f"  Impossible de lire gold_final : {exc}")
    else:
        logger.warning("  gold_final.parquet absent — étape gold_final échouée ?")

    # ── Chargement PostgreSQL ─────────────────────────────────────────────
    pg_status = "skipped_dry_run"
    pg_rows: dict = {}

    if not dry_run:
        logger.info("\n▶ Mise à jour PostgreSQL (UPSERT idempotent)")
        try:
            from pipeline.load_postgres import (
                seed_arrondissements,
                load_prix_median,
                load_logements_sociaux,
                load_indicateurs,
            )
            from db.postgres import init_schema, session_scope

            init_schema()
            with session_scope() as s:
                pg_rows["arrondissements"] = seed_arrondissements(s)
                pg_rows["prix_median"]     = load_prix_median(s)
                pg_rows["logements_soc"]   = load_logements_sociaux(s)
                pg_rows["indicateurs"]     = load_indicateurs(s)

            pg_status = "ok"
            logger.success(f"  ✓ PostgreSQL mis à jour : {pg_rows}")
        except Exception as exc:
            pg_status = f"error: {exc}"
            logger.error(f"  ✗ PostgreSQL : {exc}")
    else:
        logger.info("  (DRY-RUN — chargement PostgreSQL ignoré)")

    # ── Rapport final ─────────────────────────────────────────────────────
    stats    = collect_stats()
    duration = round(time.time() - t0, 2)
    end_iso  = datetime.now(timezone.utc).isoformat()

    n_errors   = sum(1 for s in steps_results.values() if s["status"] == "error")
    n_partial  = sum(1 for s in steps_results.values() if s["status"] == "partial")
    batch_status = "error" if n_errors > 0 else ("partial" if n_partial > 0 else "success")

    report = {
        "batch_id":        batch_id,
        "start_time":      start_iso,
        "end_time":        end_iso,
        "duration_seconds": duration,
        "status":          batch_status,
        "dry_run":         dry_run,
        "steps":           steps_results,
        "stats":           stats,
        "postgres":        {"status": pg_status, "rows_updated": pg_rows},
        "anomalies":       anomalies,
        "anomalies_count": len(anomalies),
        "errors_count":    n_errors,
    }

    # Écrit le rapport horodaté + un pointeur "dernier rapport"
    report_path = REPORTS_DIR / f"report_{batch_id}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    LAST_REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    logger.info("\n" + "=" * 62)
    logger.info(f"  BATCH {'DRY-RUN ' if dry_run else ''}TERMINÉ  [{batch_status.upper()}]")
    logger.info(f"  Durée        : {duration:.1f}s")
    logger.info(f"  Transactions : {stats['nb_transactions_total']:,}")
    logger.info(f"  Prix médian  : {stats['prix_m2_median_paris']:,.0f} €/m²" if stats['prix_m2_median_paris'] else "  Prix médian  : N/A")
    logger.info(f"  Anomalies    : {len(anomalies)}")
    logger.info(f"  Rapport      : {report_path.relative_to(ROOT)}")
    logger.info("=" * 62)

    return report


# ── Mode daemon APScheduler ───────────────────────────────────────────────────

def run_scheduler():
    """Lance APScheduler : batch DVF chaque nuit à 02h00 Europe/Paris."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("APScheduler non installé → pip install apscheduler>=3.10")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="Europe/Paris")
    trigger = CronTrigger(hour=2, minute=0, timezone="Europe/Paris")
    scheduler.add_job(
        run_batch,
        trigger=trigger,
        id="batch_dvf_nightly",
        name="Batch DVF nightly",
        replace_existing=True,
        misfire_grace_time=3600,   # tolère 1h de retard (redémarrage)
    )

    # Calcule le prochain déclenchement sans dépendre d'un attribut non-garanti
    # avant le démarrage du scheduler (next_run_time peut être None avant start())
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    _tz_paris = ZoneInfo("Europe/Paris")
    _now = _dt.now(_tz_paris)
    _next = _now.replace(hour=2, minute=0, second=0, microsecond=0)
    if _next <= _now:
        from datetime import timedelta as _td
        _next += _td(days=1)

    logger.info("=" * 62)
    logger.info("  SCHEDULER APScheduler démarré — Urban Data Explorer")
    logger.info("  Fréquence   : chaque nuit à 02h00 Europe/Paris")
    logger.info(f"  Prochain    : {_next.strftime('%Y-%m-%d 02:00 Europe/Paris')}")
    logger.info("  Arrêt       : Ctrl+C")
    logger.info("=" * 62)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler arrêté proprement.")


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Urban Data Explorer — Batch Processor DVF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python3 pipeline/batch_processor.py              # batch immédiat\n"
            "  python3 pipeline/batch_processor.py --schedule   # daemon nightly\n"
            "  python3 pipeline/batch_processor.py --dry-run    # sans écriture PG\n"
        ),
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Mode daemon : APScheduler batch chaque nuit à 02h00",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Analyse sans écriture dans PostgreSQL",
    )
    args = parser.parse_args()

    if args.schedule:
        run_scheduler()
    else:
        run_batch(dry_run=args.dry_run)
