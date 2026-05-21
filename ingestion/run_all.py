"""
ingestion/run_all.py — Urban Data Explorer
Lance les 13 scripts d'ingestion dans l'ordre.
Usage : python ingestion/run_all.py
"""
import sys, time
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.geo_arrondissements import run as run_geo
from ingestion.dvf_prix            import run as run_dvf
from ingestion.logements_sociaux   import run as run_rpls
from ingestion.transports          import run as run_transports
from ingestion.education           import run as run_education
from ingestion.parcs_osm           import run as run_parcs
from ingestion.criminalite         import run as run_crime
from ingestion.loyers              import run as run_loyers
from ingestion.revenus_insee       import run as run_revenus
from ingestion.qualite_air         import run as run_air
from ingestion.commerces_sante     import run as run_commerces
from ingestion.bruit               import run as run_bruit
from ingestion.circulation         import run as run_circulation

TASKS = [
    ("Contours géographiques",        run_geo),
    ("DVF — prix immobiliers",        run_dvf),
    ("Logements sociaux (RPLS)",      run_rpls),
    ("Transports (IDFM)",             run_transports),
    ("Éducation",                     run_education),
    ("Parcs et espaces verts (OSM)",  run_parcs),
    ("Criminalité",                   run_crime),
    ("Loyers de référence (DRIHL)",   run_loyers),
    ("Revenus INSEE Filosofi",        run_revenus),
    ("Qualité de l'air (AIRPARIF)",   run_air),
    ("Commerces et santé (OSM/SIRENE)", run_commerces),
    ("Bruit (BRUITPARIF)",            run_bruit),
    ("Circulation / trafic (Paris)",  run_circulation),
]


def main():
    logger.info("=" * 62)
    logger.info("  URBAN DATA EXPLORER — Ingestion Bronze (13 sources)")
    logger.info("=" * 62)

    results = {}
    t0 = time.time()
    for name, fn in TASKS:
        logger.info(f"\n▶ {name}")
        t_start = time.time()
        try:
            ok = fn()
            results[name] = "✓" if ok else "⚠ partiel"
        except Exception as e:
            logger.error(f"  Erreur : {e}")
            results[name] = "✗ erreur"
        logger.info(f"  ({time.time() - t_start:.1f}s)")

    logger.info("\n" + "=" * 62)
    logger.info("  RÉSUMÉ")
    logger.info("=" * 62)
    for name, status in results.items():
        logger.info(f"  {status}  {name}")

    ok_count = sum(1 for s in results.values() if s.startswith("✓"))
    logger.info(f"\n  {ok_count}/{len(TASKS)} sources ingérées en {time.time()-t0:.0f}s")
    logger.info("  → Suite : python pipeline/run_pipeline.py")


if __name__ == "__main__":
    main()
