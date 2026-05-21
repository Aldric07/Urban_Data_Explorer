"""
pipeline/check_datalake.py
Vérifie l'état de santé complet du Data Lake Bronze/Silver/Gold.
Affiche un tableau de bord de tous les fichiers, leur taille, nb lignes,
et signale les fichiers manquants ou vides.
Usage : python pipeline/check_datalake.py
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, GOLD_DIR


def file_info(path: Path) -> dict:
    """Retourne les infos d'un fichier (taille, lignes, dernière modif)."""
    if not path.exists():
        return {"status": "❌ ABSENT", "size": "-", "rows": "-", "modified": "-"}

    size = path.stat().st_size
    size_str = f"{size/1e6:.1f} Mo" if size > 1e6 else f"{size/1e3:.0f} Ko"
    modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m %H:%M")

    rows = "-"
    if path.suffix == ".parquet":
        try:
            df = pd.read_parquet(path)
            rows = f"{len(df):,}"
            if len(df) == 0:
                return {"status": "⚠️  VIDE", "size": size_str, "rows": "0", "modified": modified}
        except Exception:
            return {"status": "⚠️  CORROMPU", "size": size_str, "rows": "?", "modified": modified}
    elif path.suffix in [".csv", ".json"]:
        try:
            rows = f"~{path.stat().st_size // 100}" # Estimation rapide
        except Exception:
            pass

    return {"status": "✅ OK", "size": size_str, "rows": rows, "modified": modified}


def print_section(title: str, files: list[tuple[str, Path]]):
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"{'─'*70}")
    print(f"  {'Fichier':<40} {'Status':<15} {'Taille':>8}  {'Lignes':>10}  {'Modifié'}")
    print(f"  {'─'*38} {'─'*13} {'─'*8}  {'─'*10}  {'─'*12}")
    for label, path in files:
        info = file_info(path)
        print(
            f"  {label:<40} {info['status']:<15} {info['size']:>8}  "
            f"{info['rows']:>10}  {info['modified']}"
        )


def run():
    print("\n" + "═"*70)
    print("  URBAN DATA EXPLORER — État du Data Lake")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("═"*70)

    # ── Bronze ──────────────────────────────────────────────────────────────
    bronze_files = [
        ("geo_arrondissements.geojson",   BRONZE_DIR / "geo_arrondissements.geojson"),
        ("logements_sociaux_paris.csv",   BRONZE_DIR / "logements_sociaux_paris.csv"),
        ("transports_idf_arrets.json",    BRONZE_DIR / "transports_idf_arrets.json"),
        ("education_paris.json",          BRONZE_DIR / "education_paris.json"),
        ("parcs_paris_osm.json",          BRONZE_DIR / "parcs_paris_osm.json"),
        ("criminalite_paris.csv",         BRONZE_DIR / "criminalite_paris.csv"),
        ("loyers_reference_paris.csv",    BRONZE_DIR / "loyers_reference_paris.csv"),
        ("revenus_insee_paris.csv",       BRONZE_DIR / "revenus_insee_paris.csv"),
        ("qualite_air_paris.json",        BRONZE_DIR / "qualite_air_paris.json"),
    ]
    # DVF par année
    from config import DVF_YEARS
    for year in DVF_YEARS:
        bronze_files.append((
            f"dvf/dvf_75_{year}.csv.gz",
            BRONZE_DIR / "dvf" / f"dvf_75_{year}.csv.gz"
        ))
    print_section("BRONZE — Données brutes", bronze_files)

    # ── Silver ──────────────────────────────────────────────────────────────
    silver_files = [
        ("geo_arrondissements.geojson",  SILVER_DIR / "geo_arrondissements.geojson"),
        ("geo_arrondissements.parquet",  SILVER_DIR / "geo_arrondissements.parquet"),
        ("dvf/dvf_all.parquet",          SILVER_DIR / "dvf" / "dvf_all.parquet"),
        ("logements_sociaux.parquet",    SILVER_DIR / "logements_sociaux.parquet"),
        ("transports.parquet",           SILVER_DIR / "transports.parquet"),
        ("education.parquet",            SILVER_DIR / "education.parquet"),
        ("parcs.parquet",                SILVER_DIR / "parcs.parquet"),
        ("criminalite.parquet",          SILVER_DIR / "criminalite.parquet"),
        ("loyers.parquet",               SILVER_DIR / "loyers.parquet"),
        ("revenus.parquet",              SILVER_DIR / "revenus.parquet"),
        ("qualite_air.parquet",          SILVER_DIR / "qualite_air.parquet"),
    ]
    print_section("SILVER — Données nettoyées (Parquet)", silver_files)

    # ── Gold ────────────────────────────────────────────────────────────────
    gold_files = [
        ("agregats_arrondissements.parquet", GOLD_DIR / "agregats_arrondissements.parquet"),
        ("indicateurs_custom.parquet",       GOLD_DIR / "indicateurs_custom.parquet"),
        ("gold_final.parquet",               GOLD_DIR / "gold_final.parquet"),
        ("stream_consolidated.parquet",      GOLD_DIR / "stream_consolidated.parquet"),
    ]
    print_section("GOLD — Agrégats prêts API", gold_files)

    # ── Résumé ───────────────────────────────────────────────────────────────
    all_files = bronze_files + silver_files + gold_files
    total  = len(all_files)
    ok     = sum(1 for _, p in all_files if p.exists() and p.stat().st_size > 0)
    absent = sum(1 for _, p in all_files if not p.exists())
    vide   = total - ok - absent

    print(f"\n{'═'*70}")
    print(f"  Résumé : {ok}/{total} fichiers OK | {absent} absents | {vide} vides/corrompus")
    if absent > 0:
        print(f"\n  → Pour compléter : python ingestion/run_all.py")
    if (absent + vide) > 0:
        print(f"  → Pour transformer : python pipeline/run_pipeline.py")
    print(f"{'═'*70}\n")


if __name__ == "__main__":
    run()
