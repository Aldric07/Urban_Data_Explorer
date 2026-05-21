"""
pipeline/streaming_microbatch.py
Implémente un système de micro-batch (C2.2) :
Simule un ingestion continue en interrogeant une API toutes les N secondes
et en écrivant des fichiers Parquet incrémentaux horodatés.

En production : remplacer la source simulée par une API live (AIRPARIF, transactions,
etc.). Le pattern micro-batch est identique quel que soit la source.

Compétence validée : C2.2 (traitement en micro-batch)
Usage :
    # Mode démo (10 batchs, 5s entre chaque)
    python pipeline/streaming_microbatch.py --batches 10 --interval 5

    # Mode continu (Ctrl+C pour arrêter)
    python pipeline/streaming_microbatch.py --continuous --interval 30
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GOLD_DIR

STREAM_DIR = GOLD_DIR / "stream"
STREAM_DIR.mkdir(exist_ok=True)

# Fichier de log des batchs traités (métadonnées pipeline)
BATCH_LOG = STREAM_DIR / "_batch_log.jsonl"


# ── Source simulée ────────────────────────────────────────────────────────────
def fetch_batch_simulated(batch_id: int) -> list[dict]:
    """
    Simule un appel API retournant ~5-15 nouvelles transactions immobilières.
    En production : remplacer par requests.get(url).json()
    """
    n = random.randint(5, 15)
    now = datetime.now(timezone.utc)
    arrondissements = list(range(1, 21))
    types = ["Appartement", "Appartement", "Appartement", "Maison"]
    records = []
    for _ in range(n):
        arr = random.choice(arrondissements)
        surface = round(random.uniform(20, 150), 1)
        # Prix réalistes par arrondissement
        base_prix = {
            1: 14000, 2: 13000, 3: 12500, 4: 13500, 5: 13000,
            6: 15000, 7: 14500, 8: 13500, 9: 11000, 10: 10500,
            11: 10500, 12: 10000, 13: 9500, 14: 10000, 15: 10500,
            16: 12000, 17: 11500, 18: 10000, 19: 9000, 20: 9500,
        }
        prix_m2 = base_prix[arr] * random.uniform(0.85, 1.15)
        records.append({
            "batch_id":      batch_id,
            "timestamp":     now.isoformat(),
            "arrondissement": arr,
            "type_local":    random.choice(types),
            "surface_m2":    surface,
            "prix_m2":       round(prix_m2, 0),
            "valeur":        round(prix_m2 * surface, 0),
        })
    return records


# ── Traitement d'un batch ─────────────────────────────────────────────────────
def process_batch(batch_id: int, records: list[dict]) -> Path:
    """Transforme un batch brut et l'écrit en Parquet horodaté."""
    df = pd.DataFrame(records)

    # Agrégat rapide par arrondissement (niveau Gold streaming)
    agg = (
        df.groupby("arrondissement")
        .agg(
            nb_transactions=("prix_m2", "count"),
            prix_m2_median=("prix_m2", "median"),
            prix_m2_moyen=("prix_m2", "mean"),
        )
        .reset_index()
    )
    agg["batch_id"]  = batch_id
    agg["timestamp"] = df["timestamp"].iloc[0]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = STREAM_DIR / f"batch_{batch_id:06d}_{ts}.parquet"
    agg.to_parquet(dest, index=False)
    return dest


def log_batch(batch_id: int, n_records: int, dest: Path, elapsed: float):
    """Enregistre les métadonnées de chaque batch dans un fichier JSONL."""
    entry = {
        "batch_id":   batch_id,
        "ts":         datetime.now(timezone.utc).isoformat(),
        "n_records":  n_records,
        "output":     dest.name,
        "elapsed_ms": round(elapsed * 1000, 1),
    }
    with open(BATCH_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def consolidate_stream() -> Path:
    """Consolide tous les batchs en un seul Parquet Gold stream."""
    files = sorted(STREAM_DIR.glob("batch_*.parquet"))
    if not files:
        return None
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    # Moyenne glissante des agrégats
    df_final = (
        df.groupby("arrondissement")
        .agg(
            nb_transactions_total=("nb_transactions", "sum"),
            prix_m2_median_stream=("prix_m2_median", "median"),
            nb_batchs=("batch_id", "nunique"),
        )
        .reset_index()
    )
    dest = GOLD_DIR / "stream_consolidated.parquet"
    df_final.to_parquet(dest, index=False)
    logger.info(f"  Stream consolidé → {dest.name} ({len(df_final)} arrondissements)")
    return dest


# ── Orchestration ─────────────────────────────────────────────────────────────
def run_stream(n_batches: int = None, interval_seconds: int = 5):
    """
    Lance le streaming micro-batch.
    n_batches=None → continu jusqu'à Ctrl+C.
    """
    logger.info("=" * 55)
    logger.info("  STREAMING MICRO-BATCH — Urban Data Explorer")
    logger.info(f"  Intervalle : {interval_seconds}s | Mode : {'continu' if n_batches is None else f'{n_batches} batchs'}")
    logger.info("=" * 55)

    batch_id = 0
    total_records = 0

    try:
        while n_batches is None or batch_id < n_batches:
            batch_id += 1
            t0 = time.time()

            # 1. Fetch (source simulée ou API réelle)
            records = fetch_batch_simulated(batch_id)

            # 2. Traitement
            dest = process_batch(batch_id, records)

            elapsed = time.time() - t0
            total_records += len(records)
            log_batch(batch_id, len(records), dest, elapsed)

            logger.info(
                f"  Batch {batch_id:04d} | {len(records):3d} records | "
                f"{elapsed*1000:.0f}ms | {dest.name}"
            )

            if n_batches and batch_id >= n_batches:
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("\n  Arrêt demandé (Ctrl+C)")

    # Consolidation finale
    logger.info(f"\n  Total : {batch_id} batchs, {total_records} records")
    consolidate_stream()
    logger.success("  ✓ Streaming terminé")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Streaming micro-batch Urban Data Explorer")
    parser.add_argument("--batches",    type=int, default=10,  help="Nombre de batchs (défaut: 10)")
    parser.add_argument("--interval",  type=int, default=2,   help="Secondes entre batchs (défaut: 2)")
    parser.add_argument("--continuous", action="store_true",   help="Mode continu (Ctrl+C pour arrêter)")
    args = parser.parse_args()

    n = None if args.continuous else args.batches
    run_stream(n_batches=n, interval_seconds=args.interval)
