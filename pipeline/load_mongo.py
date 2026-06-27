"""
pipeline/load_mongo.py — Charge Bronze + métadonnées + streams dans MongoDB.

Trois collections alimentées :

1. **bronze_raw** : un document par fichier Bronze, contient le payload brut
   (parsé JSON pour les .json, lignes échantillonnées pour les CSV) + métadonnées
   d'ingestion. Justifie le choix NoSQL : chaque source a un schéma différent,
   on ne tente pas de tout aplatir.

2. **data_catalog** : une entrée par source (URL, taille, nb lignes, fraîcheur,
   indicateurs qualité). C'est le « data catalog mini » exigé dans les livrables.

3. **stream_events** : événements consolidés du micro-batch (lus depuis
   stream_consolidated.parquet). Index TTL natif pour la rétention.

Compétences couvertes : C1.2 (NoSQL), C1.3 (Data Lake — Bronze stocké aussi en
DB pour traçabilité/versioning), C2.3 (intégration multi-sources).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger
from pymongo import UpdateOne

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, GOLD_DIR
from db.mongo import bronze, catalog, init_indexes, stream

# Échantillon max pour les gros CSV (DVF) — Mongo n'est pas la cible pour le
# stockage de masse, Postgres l'est. Bronze sert ici à la traçabilité/audit.
MAX_CSV_SAMPLE_ROWS = 500


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_bronze_files():
    """Itère sur tous les fichiers Bronze (récursif, hors caches)."""
    for p in BRONZE_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in {".json", ".csv", ".geojson"}:
            continue
        yield p


def load_bronze() -> int:
    """Indexe chaque fichier Bronze dans Mongo (upsert par chemin relatif)."""
    ops = []
    now = datetime.now(timezone.utc)

    for path in _iter_bronze_files():
        rel = str(path.relative_to(BRONZE_DIR))
        size = path.stat().st_size
        checksum = _checksum(path)

        doc = {
            "source": rel.split("/")[0] if "/" in rel else rel,
            "path": rel,
            "format": path.suffix.lstrip(".").lower(),
            "size_bytes": size,
            "checksum": checksum,
            "ingested_at": now,
        }

        # Lecture du contenu selon le format
        try:
            if path.suffix.lower() in {".json", ".geojson"}:
                content = json.loads(path.read_text())
                if isinstance(content, dict) and "features" in content:
                    doc["payload_kind"] = "geojson"
                    doc["nb_features"] = len(content["features"])
                    # Pas de payload complet pour les GeoJSON volumineux
                    doc["sample"] = content["features"][:3]
                else:
                    doc["payload_kind"] = "json"
                    doc["payload"] = content if size < 256_000 else None
                    doc["sample"] = content if isinstance(content, list) else [content]
                    if isinstance(doc["sample"], list):
                        doc["sample"] = doc["sample"][:5]
            elif path.suffix.lower() == ".csv":
                df_sample = pd.read_csv(
                    path, sep=None, engine="python", nrows=MAX_CSV_SAMPLE_ROWS, encoding_errors="replace"
                )
                doc["payload_kind"] = "csv"
                doc["columns"] = list(df_sample.columns)
                doc["nb_rows_sample"] = len(df_sample)
                doc["sample"] = df_sample.head(5).to_dict(orient="records")
        except Exception as e:
            logger.warning(f"  ⚠ lecture impossible {rel} : {e}")
            doc["error"] = str(e)

        ops.append(UpdateOne({"path": rel}, {"$set": doc}, upsert=True))

    if not ops:
        return 0
    bronze().create_index("path", unique=True)
    result = bronze().bulk_write(ops, ordered=False)
    return (result.upserted_count or 0) + (result.modified_count or 0)


def load_catalog() -> int:
    """Construit le data catalog (une entrée agrégée par source)."""
    # Agrégation depuis bronze_raw (Mongo) — pipeline NoSQL natif
    pipeline = [
        {"$group": {
            "_id": "$source",
            "nb_fichiers": {"$sum": 1},
            "taille_totale_bytes": {"$sum": "$size_bytes"},
            "derniere_ingestion": {"$max": "$ingested_at"},
            "formats": {"$addToSet": "$format"},
            "exemple_chemin": {"$first": "$path"},
        }},
    ]
    agg = list(bronze().aggregate(pipeline))

    # Mapping source → métadonnées humaines (justification & qualité)
    DESCRIPTIONS = {
        "dvf": ("Demandes de Valeurs Foncières", "data.gouv.fr / DGFiP",
                "Transactions immobilières 2021-2024, prix au m²"),
        "geo_arrondissements.geojson": ("Contours arrondissements", "OpenData Paris",
                                        "Géométries des 20 arrondissements (4326)"),
        "logements_sociaux_paris.csv": ("Logements sociaux RPLS", "data.gouv.fr",
                                        "Parc social bailleurs sociaux"),
        "revenus_insee_paris.csv": ("Revenus INSEE Filosofi", "INSEE",
                                    "Revenus médian par commune/IRIS"),
        "loyers_reference_paris.csv": ("Encadrement des loyers", "OpenData Paris",
                                       "Loyers de référence par quartier"),
        "transports_idf_arrets.json": ("Arrêts IDFM", "Île-de-France Mobilités",
                                       "Gares & arrêts Métro/RER/Bus"),
        "education_paris.json": ("Annuaire de l'éducation", "data.education.gouv.fr",
                                 "Écoles, collèges, lycées"),
        "commerces_paris.json": ("Commerces OSM", "OpenStreetMap Overpass",
                                 "Supermarchés, boulangeries, pharmacies"),
        "sante_paris.json": ("Établissements de santé OSM", "OpenStreetMap Overpass",
                             "Hôpitaux, cliniques, médecins"),
        "parcs_paris_osm.json": ("Parcs et jardins OSM", "OpenStreetMap Overpass",
                                 "Espaces verts publics"),
        "qualite_air_paris.json": ("Qualité de l'air", "AIRPARIF",
                                   "Indices NO2, PM10, PM2.5"),
        "bruit_paris.json": ("Bruit", "OpenData Paris", "Cartographie sonore"),
        "circulation_paris.json": ("Circulation", "OpenData Paris",
                                   "Comptages routiers temps réel"),
        "criminalite_paris.csv": ("Délinquance enregistrée", "SSMSI / Intérieur",
                                  "Faits constatés par commune et catégorie"),
    }

    ops = []
    now = datetime.now(timezone.utc)
    for entry in agg:
        source = entry["_id"]
        label, fournisseur, description = DESCRIPTIONS.get(
            source, (source, "inconnu", "")
        )
        derniere = entry.get("derniere_ingestion")
        # Filet de sécurité si Mongo renvoie une datetime naïve : on la rend aware.
        if derniere is not None and derniere.tzinfo is None:
            derniere = derniere.replace(tzinfo=timezone.utc)
        doc = {
            "source": source,
            "libelle": label,
            "fournisseur": fournisseur,
            "description": description,
            "nb_fichiers": entry["nb_fichiers"],
            "taille_totale_bytes": entry["taille_totale_bytes"],
            "derniere_ingestion": derniere,
            "formats": entry["formats"],
            "exemple_chemin": entry["exemple_chemin"],
            "qualite": {
                "fraicheur_jours": (now - derniere).days if derniere else None,
                "complet": entry["nb_fichiers"] > 0,
            },
            "updated_at": now,
        }
        ops.append(UpdateOne({"source": source}, {"$set": doc}, upsert=True))

    if not ops:
        return 0
    result = catalog().bulk_write(ops, ordered=False)
    return (result.upserted_count or 0) + (result.modified_count or 0)


def load_stream_events() -> int:
    """Charge les événements de stream consolidés (si présents)."""
    p = GOLD_DIR / "stream_consolidated.parquet"
    if not p.exists():
        return 0

    df = pd.read_parquet(p)
    if df.empty:
        return 0

    now = datetime.now(timezone.utc)
    docs = []
    for r in df.to_dict(orient="records"):
        clean = {k: (None if pd.isna(v) else v) for k, v in r.items()}
        clean["ingested_at"] = now
        docs.append(clean)

    if not docs:
        return 0
    # Insertion simple — le TTL purgera après 30 jours
    stream().insert_many(docs, ordered=False)
    return len(docs)


def main():
    logger.info("──────────────────────────────────────────────")
    logger.info("  Chargement Bronze + métadonnées → MongoDB")
    logger.info("──────────────────────────────────────────────")

    logger.info("1. Création des index Mongo")
    init_indexes()
    logger.info("   ✓ indexes prêts")

    logger.info("2. Chargement Bronze (fichiers bruts → bronze_raw)")
    n = load_bronze()
    logger.info(f"   ✓ {n} documents upsertés")

    logger.info("3. Construction du data catalog")
    n = load_catalog()
    logger.info(f"   ✓ {n} sources cataloguées")

    logger.info("4. Chargement événements de streaming")
    n = load_stream_events()
    logger.info(f"   ✓ {n} événements insérés")

    logger.info("✓ Chargement MongoDB terminé")


if __name__ == "__main__":
    main()
