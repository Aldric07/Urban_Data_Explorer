
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import BRONZE_DIR, MONGO_URI, MONGO_DB_NAME

# ── Constantes ────────────────────────────────────────────────────────────────

COLLECTION_STREAM = "stream_events"
ALERT_ORANGE = 75    # IQA seuil alerte modérée (norme française)
ALERT_RED    = 100   # IQA seuil alerte forte

# API WFS publique Airparif — indice agrégé Île-de-France, sans clé
WFS_URL = (
    "https://magellan.airparif.asso.fr/geoserver/DIDON/ows"
    "?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=DIDON:ind_idf_agglo&outputFormat=application/json&maxFeatures=50"
)

# Valeurs de référence IQA par arrondissement (données AIRPARIF historiques 2023)
# IQA : 0-50 bon, 51-100 moyen, 101-150 dégradé, > 150 mauvais
IQA_BASE: dict[int, float] = {
    1: 52,  2: 54,  3: 50,  4: 51,  5: 48,
    6: 47,  7: 45,  8: 58,  9: 56,  10: 55,
    11: 53, 12: 49, 13: 51, 14: 47, 15: 48,
    16: 44, 17: 53, 18: 62, 19: 64, 20: 60,
}

# NO2 µg/m³ de référence (corrélé à l'IQA)
NO2_BASE: dict[int, float] = {
    1: 38, 2: 40, 3: 36, 4: 37, 5: 34,
    6: 33, 7: 31, 8: 44, 9: 42, 10: 41,
    11: 39, 12: 35, 13: 37, 14: 33, 15: 34,
    16: 30, 17: 39, 18: 48, 19: 50, 20: 46,
}

# PM2.5 µg/m³ de référence
PM25_BASE: dict[int, float] = {
    1: 12, 2: 13, 3: 11, 4: 12, 5: 10,
    6: 10, 7: 9,  8: 14, 9: 13, 10: 13,
    11: 12, 12: 11, 13: 12, 14: 10, 15: 10,
    16: 9,  17: 12, 18: 16, 19: 17, 20: 15,
}


# ── Agrégat glissant 24h en mémoire ──────────────────────────────────────────

class RollingWindow24h:
    """Maintient les N dernières mesures (24h) par arrondissement."""

    def __init__(self, window_hours: int = 24):
        self.window = timedelta(hours=window_hours)
        self._data: dict[int, deque] = defaultdict(deque)

    def push(self, arr: int, iqa: float, ts: datetime):
        self._data[arr].append((ts, iqa))
        cutoff = datetime.now(timezone.utc) - self.window
        while self._data[arr] and self._data[arr][0][0] < cutoff:
            self._data[arr].popleft()

    def mean_24h(self, arr: int) -> Optional[float]:
        if not self._data[arr]:
            return None
        vals = [v for _, v in self._data[arr]]
        return round(sum(vals) / len(vals), 1)

    def all_means(self) -> dict[int, float]:
        return {arr: self.mean_24h(arr) for arr in range(1, 21)}


_window = RollingWindow24h()


# ── Sources de données ────────────────────────────────────────────────────────

def _load_bronze_base() -> dict[int, dict]:
    """Charge les valeurs Bronze AIRPARIF comme référence."""
    path = BRONZE_DIR / "qualite_air_paris.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        if "arrondissements" in raw:
            return {
                int(k): v
                for k, v in raw["arrondissements"].items()
                if k.isdigit() and 1 <= int(k) <= 20
            }
    except Exception:
        pass
    return {}


def _time_factor() -> float:
    """
    Facteur multiplicatif IQA selon l'heure locale (rush hours).
    Rush matin 7-9h → +20%, rush soir 17-19h → +18%, nuit 0-5h → -15%.
    """
    hour = datetime.now().hour
    if 7 <= hour <= 9:
        return 1.20
    elif 17 <= hour <= 19:
        return 1.18
    elif 12 <= hour <= 14:
        return 1.05
    elif 0 <= hour <= 5:
        return 0.85
    else:
        return 1.0


def fetch_airparif_live() -> Optional[list[dict]]:
    """
    Interroge l'API WFS publique Airparif (sans clé).
    Récupère l'indice IQA agrégé île-de-France le plus récent et le distribue
    proportionnellement sur les 20 arrondissements via les ratios IQA_BASE.
    Retourne None si l'appel échoue ou si features est vide.
    """
    try:
        resp = requests.get(WFS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None

        latest = max(features, key=lambda f: f.get("properties", {}).get("date_ech") or "")
        props = latest.get("properties", {})

        iqa_global  = float(props.get("valeur")   or 0)
        no2_global  = float(props.get("val_no2")  or 0)
        pm25_global = float(props.get("val_pm25") or 0)

        if iqa_global <= 0:
            return None

        mean_iqa  = sum(IQA_BASE.values())  / len(IQA_BASE)
        mean_no2  = sum(NO2_BASE.values())  / len(NO2_BASE)
        mean_pm25 = sum(PM25_BASE.values()) / len(PM25_BASE)

        results = []
        for arr in range(1, 21):
            results.append({
                "insee": f"751{arr:02d}",
                "iqa":   round(iqa_global  * (IQA_BASE[arr]  / mean_iqa),  1),
                "no2":   round(no2_global  * (NO2_BASE[arr]  / mean_no2),  1),
                "pm25":  round(pm25_global * (PM25_BASE[arr] / mean_pm25), 1),
            })
        return results

    except Exception as exc:
        logger.error(f"  fetch_airparif_live WFS error : {exc}")
        return None


def fetch_with_bronze_fallback() -> list[dict]:
    """
    Construit les mesures depuis les données Bronze + variation temporelle.
    Fallback déterministe et réaliste.
    """
    bronze_base = _load_bronze_base()
    factor = _time_factor()
    # Événement de pollution ponctuel (~10% des cycles)
    pollution_event = random.random() < 0.10
    event_arr = random.randint(1, 20) if pollution_event else None

    results = []
    for arr in range(1, 21):
        b = bronze_base.get(arr, {})

        base_iqa  = float(b.get("iqa_moyen", IQA_BASE[arr]))
        base_no2  = float(b.get("no2_µg_m3", NO2_BASE[arr]))
        base_pm25 = float(b.get("pm25_µg_m3", PM25_BASE[arr]))

        # Variation temporelle + bruit gaussien ±5 IQA
        noise = random.gauss(0, 4)
        event_bonus = random.uniform(25, 50) if arr == event_arr else 0.0

        iqa  = round(base_iqa  * factor + noise + event_bonus, 1)
        no2  = round(base_no2  * factor + random.gauss(0, 2) + event_bonus * 0.4, 1)
        pm25 = round(base_pm25 * factor + random.gauss(0, 1) + event_bonus * 0.15, 1)

        # Borne physique
        iqa  = max(0, min(200, iqa))
        no2  = max(0, no2)
        pm25 = max(0, pm25)

        results.append({
            "arrondissement": arr,
            "iqa":   iqa,
            "no2":   no2,
            "pm25":  pm25,
            "source": "bronze_fallback",
        })

    if pollution_event:
        logger.debug(f"  [simulation] Événement pollution arr.{event_arr}")

    return results


def fetch_measurements() -> tuple[list[dict], str]:
    """
    Tente l'API live AIRPARIF, sinon Bronze + simulation.
    Retourne (mesures, source_name).
    """
    live = fetch_airparif_live()
    if live:
        logger.debug("  Source : AIRPARIF live API")
        # Normalise le format AIRPARIF live vers notre structure interne
        results = []
        for rec in live:
            commune = str(rec.get("commune_code", "") or rec.get("insee", ""))
            if commune.startswith("751") and len(commune) == 5:
                try:
                    arr = int(commune[-2:].lstrip("0") or "0")
                    if 1 <= arr <= 20:
                        results.append({
                            "arrondissement": arr,
                            "iqa":   float(rec.get("indice") or rec.get("iqa") or IQA_BASE[arr]),
                            "no2":   float(rec.get("no2") or NO2_BASE[arr]),
                            "pm25":  float(rec.get("pm25") or rec.get("pm2_5") or PM25_BASE[arr]),
                            "source": "airparif_live",
                        })
                except (ValueError, TypeError):
                    pass
        if results:
            return results, "airparif_live"

    return fetch_with_bronze_fallback(), "bronze_fallback"


# ── Traitement d'un cycle de mesures ─────────────────────────────────────────

def _classify_alert(iqa: float) -> Optional[str]:
    if iqa > ALERT_RED:
        return "rouge"
    if iqa > ALERT_ORANGE:
        return "orange"
    return None


def process_cycle(measurements: list[dict], source: str) -> dict:
    """
    Enrichit les mesures (alertes, IQA catégorie), met à jour la fenêtre
    glissante et retourne le résumé du cycle.
    """
    now_utc = datetime.now(timezone.utc)
    documents = []
    alerts = []

    for m in measurements:
        arr = m["arrondissement"]
        iqa = m["iqa"]

        alert_level = _classify_alert(iqa)
        if alert_level == "rouge":
            msg = f"POLLUTION FORTE — Arr.{arr} IQA={iqa:.0f} > {ALERT_RED}"
            logger.error(f"  🔴 {msg}")
            alerts.append({"arrondissement": arr, "level": "rouge", "iqa": iqa, "message": msg})
        elif alert_level == "orange":
            msg = f"Pollution modérée — Arr.{arr} IQA={iqa:.0f} > {ALERT_ORANGE}"
            logger.warning(f"  🟠 {msg}")
            alerts.append({"arrondissement": arr, "level": "orange", "iqa": iqa, "message": msg})

        _window.push(arr, iqa, now_utc)

        documents.append({
            "type":          "air_quality",
            "source":        source,
            "ingested_at":   now_utc,
            "timestamp":     now_utc,
            "arrondissement": arr,
            "iqa":           iqa,
            "no2_µg_m3":    m.get("no2"),
            "pm25_µg_m3":   m.get("pm25"),
            "alert_level":   alert_level,
            "iqa_24h_mean":  _window.mean_24h(arr),
        })

    return {
        "timestamp":   now_utc.isoformat(),
        "source":      source,
        "n_mesures":   len(documents),
        "alerts":      alerts,
        "documents":   documents,
    }


# ── Écriture MongoDB ──────────────────────────────────────────────────────────

def write_to_mongo(documents: list[dict]) -> int:
    """Insère les mesures dans MongoDB stream_events. Retourne le nb d'insertions."""
    try:
        from pymongo import MongoClient
        from datetime import timezone as tz

        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=3000,
            tz_aware=True,
            tzinfo=timezone.utc,
        )
        col = client[MONGO_DB_NAME][COLLECTION_STREAM]

        # Index de recherche par type + arrondissement (TTL géré par db/mongo.py)
        col.create_index(
            [("type", 1), ("arrondissement", 1), ("ingested_at", -1)],
            background=True,
        )

        result = col.insert_many(documents)
        client.close()
        return len(result.inserted_ids)
    except Exception as exc:
        logger.error(f"  MongoDB write error : {exc}")
        return 0


# ── Boucle principale ─────────────────────────────────────────────────────────

def run_streaming(interval_seconds: int = 30, once: bool = False):
    """
    Lance la boucle de streaming qualité de l'air.
    interval_seconds : délai entre deux polls (défaut 30s).
    once             : exécute un seul cycle puis s'arrête.
    """
    mode = "UN SEUL CYCLE" if once else f"continu (intervalle {interval_seconds}s)"
    logger.info("=" * 62)
    logger.info("  STREAMING AIR QUALITY — Urban Data Explorer")
    logger.info(f"  Mode    : {mode}")
    logger.info(f"  Seuils  : orange > {ALERT_ORANGE} IQA | rouge > {ALERT_RED} IQA")
    logger.info(f"  MongoDB : {MONGO_DB_NAME}.{COLLECTION_STREAM}")
    logger.info("  Arrêt   : Ctrl+C")
    logger.info("=" * 62)

    cycle = 0
    total_docs = 0
    total_alerts = 0

    try:
        while True:
            cycle += 1
            t_cycle = time.time()

            logger.info(f"\n── Cycle {cycle:04d} ── {datetime.now().strftime('%H:%M:%S')} ──")

            # 1. Récupère les mesures (live ou fallback)
            measurements, source = fetch_measurements()

            # 2. Enrichit et détecte les alertes
            summary = process_cycle(measurements, source)

            # 3. Écrit dans MongoDB
            n_inserted = write_to_mongo(summary["documents"])
            total_docs   += n_inserted
            total_alerts += len(summary["alerts"])

            elapsed = time.time() - t_cycle
            alert_str = (
                f"⚠ {len(summary['alerts'])} ALERTE(S)"
                if summary["alerts"]
                else "OK"
            )
            logger.info(
                f"  [{alert_str}] source={source} "
                f"mesures={summary['n_mesures']} "
                f"mongo={n_inserted} "
                f"({elapsed*1000:.0f}ms)"
            )

            if once:
                break

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("\n  Arrêt demandé (Ctrl+C)")

    logger.info("=" * 62)
    logger.info(f"  STREAMING TERMINÉ — {cycle} cycles")
    logger.info(f"  Documents insérés : {total_docs}")
    logger.info(f"  Alertes déclenchées : {total_alerts}")
    logger.info("=" * 62)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Urban Data Explorer — Streaming qualité de l'air (AIRPARIF)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python3 pipeline/streaming_air_quality.py              # continu 30s\n"
            "  python3 pipeline/streaming_air_quality.py --once       # un seul cycle\n"
            "  python3 pipeline/streaming_air_quality.py --interval 60\n"
            "\n"
            "Variable d'env optionnelle :\n"
            "  AIRPARIF_API_KEY=<votre_clé>  active l'API live AIRPARIF\n"
        ),
    )
    parser.add_argument(
        "--interval", type=int, default=30,
        help="Secondes entre deux polls (défaut: 30)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Execute un seul cycle et s'arrête",
    )
    args = parser.parse_args()

    run_streaming(interval_seconds=args.interval, once=args.once)
