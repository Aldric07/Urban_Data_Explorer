"""
pipeline/run_pipeline.py — Urban Data Explorer
Orchestre le pipeline complet Bronze → Silver → Gold.
Usage : python pipeline/run_pipeline.py
"""
import sys, time
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.silver_dvf               import run as run_silver_dvf
from pipeline.silver_sources           import run as run_silver_sources
from pipeline.silver_logements_sociaux import run as run_silver_ls
from pipeline.silver_loyers            import run as run_silver_loyers
from pipeline.silver_revenus           import run as run_silver_revenus
from pipeline.silver_qualite_air       import run as run_silver_air
from pipeline.silver_commerces_sante   import run as run_silver_cs
from pipeline.silver_bruit             import run as run_silver_bruit
from pipeline.silver_circulation       import run as run_silver_circ
from pipeline.silver_geo_join          import run as run_geo_join
from pipeline.gold_agregats            import run as run_gold_agregats
from pipeline.gold_indicateurs         import run as run_gold_indicateurs
from pipeline.gold_final               import run as run_gold_final

STEPS = [
    # ── Silver ──────────────────────────────────────────────────────────
    ("Silver — DVF prix immobiliers",          run_silver_dvf),
    ("Silver — géo, transport, OSM",           run_silver_sources),
    ("Silver — logements sociaux",             run_silver_ls),
    ("Silver — loyers de référence",           run_silver_loyers),
    ("Silver — revenus INSEE",                 run_silver_revenus),
    ("Silver — qualité de l'air",              run_silver_air),
    ("Silver — commerces et santé",            run_silver_cs),
    ("Silver — bruit (BRUITPARIF)",            run_silver_bruit),
    ("Silver — circulation / trafic",          run_silver_circ),
    ("Silver — geo-join coordonnées→arr.",     run_geo_join),
    # ── Gold ────────────────────────────────────────────────────────────
    ("Gold  — agrégats DVF par arrondissement", run_gold_agregats),
    ("Gold  — 4 indicateurs custom complets",   run_gold_indicateurs),
    ("Gold  — consolidation finale",            run_gold_final),
]


def main():
    logger.info("=" * 65)
    logger.info("  URBAN DATA EXPLORER — Pipeline Bronze → Silver → Gold")
    logger.info("=" * 65)

    results = {}
    t0 = time.time()
    for name, fn in STEPS:
        logger.info(f"\n▶ {name}")
        t_start = time.time()
        try:
            ok = fn()
            results[name] = "✓" if ok else "⚠  partiel"
        except Exception as e:
            logger.error(f"  Erreur : {e}")
            import traceback; traceback.print_exc()
            results[name] = "✗  erreur"
        logger.info(f"  ({time.time() - t_start:.1f}s)")

    logger.info("\n" + "=" * 65)
    logger.info("  RÉSUMÉ")
    logger.info("=" * 65)
    for name, status in results.items():
        logger.info(f"  {status}  {name}")

    ok_count = sum(1 for s in results.values() if s.startswith("✓"))
    logger.info(f"\n  {ok_count}/{len(STEPS)} étapes réussies en {time.time()-t0:.0f}s")
    logger.info("  → Vérification : python pipeline/check_datalake.py")


if __name__ == "__main__":
    main()
