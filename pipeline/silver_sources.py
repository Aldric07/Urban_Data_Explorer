"""
pipeline/silver_sources.py
Nettoyage Bronze → Silver pour les sources secondaires.
Fix : parsing transports et éducation (format API v2 opendatasoft).
"""
import json, sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR


def process_transports():
    src  = BRONZE_DIR / "transports_idf_arrets.json"
    dest = SILVER_DIR / "transports.parquet"
    if not src.exists():
        logger.warning("  Transports Bronze absent")
        return

    logger.info("  Silver transports…")
    raw = json.loads(src.read_text())

    # Format API v2 opendatasoft : {"results": [...]} ou liste directe
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        records = raw.get("results", raw.get("records", []))
    else:
        records = []

    rows = []
    for r in records:
        # Gares IDF : champs possibles selon dataset
        nom = (r.get("nom_long") or r.get("stop_name") or
               r.get("nom_arret") or r.get("nom") or "")
        # Coordonnées : geo_point_2d ou stop_lat/lon
        lat, lon = None, None
        geo = r.get("geo_point_2d") or {}
        if isinstance(geo, dict):
            lat = geo.get("lat") or geo.get("latitude")
            lon = geo.get("lon") or geo.get("longitude")
        if lat is None:
            lat = r.get("stop_lat") or r.get("latitude") or r.get("y")
            lon = r.get("stop_lon") or r.get("longitude") or r.get("x")
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        rows.append({
            "nom": nom,
            "lat": lat,
            "lon": lon,
            "type": r.get("type_transport") or r.get("mode") or "",
            "arrondissement": None,
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["nom", "lat", "lon", "type", "arrondissement"]
    )
    if not df.empty:
        df = df[df["lat"].between(48.8, 48.92) & df["lon"].between(2.26, 2.42)]

    df.to_parquet(dest, index=False)
    logger.success(f"    ✓ {len(df)} arrêts → {dest.name}")


def process_education():
    src  = BRONZE_DIR / "education_paris.json"
    dest = SILVER_DIR / "education.parquet"
    if not src.exists():
        logger.warning("  Éducation Bronze absent")
        return

    logger.info("  Silver éducation…")
    raw = json.loads(src.read_text())

    # Format API v2 opendatasoft : {"results": [...]} ou liste directe
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        records = raw.get("results", raw.get("records", []))
    else:
        records = []

    rows = []
    for r in records:
        cp = str(r.get("code_postal_uai") or r.get("code_postal") or "")
        arr = None
        if cp.startswith("750") and len(cp) == 5:
            try:
                arr = int(cp[-2:].lstrip("0") or "0")
                if not 1 <= arr <= 20:
                    arr = None
            except ValueError:
                pass

        # Coordonnées
        lat = r.get("latitude") or r.get("lat")
        lon = r.get("longitude") or r.get("lon")
        geo = r.get("position") or r.get("geo_point_2d") or {}
        if isinstance(geo, dict) and lat is None:
            lat = geo.get("lat") or geo.get("latitude")
            lon = geo.get("lon") or geo.get("longitude")

        rows.append({
            "nom":            r.get("nom_etablissement") or r.get("appellation_officielle") or "",
            "type":           r.get("type_etablissement") or "",
            "code_postal":    cp,
            "arrondissement": arr,
            "statut":         r.get("statut_public_prive") or "",
            "lat":            lat,
            "lon":            lon,
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["nom", "type", "code_postal", "arrondissement", "statut", "lat", "lon"]
    )
    df = df[df["arrondissement"].notna()]
    if not df.empty:
        df["arrondissement"] = df["arrondissement"].astype(int)

    df.to_parquet(dest, index=False)
    logger.success(f"    ✓ {len(df)} établissements → {dest.name}")


def process_parcs():
    src  = BRONZE_DIR / "parcs_paris_osm.json"
    dest = SILVER_DIR / "parcs.parquet"
    if not src.exists():
        logger.warning("  Parcs Bronze absent")
        return

    logger.info("  Silver parcs…")
    raw  = json.loads(src.read_text())
    elements = raw.get("elements", [])

    rows = []
    for e in elements:
        center = e.get("center") or {}
        tags   = e.get("tags") or {}
        lat    = center.get("lat")
        lon    = center.get("lon")
        if lat is None:
            lat = e.get("lat")
            lon = e.get("lon")
        rows.append({
            "osm_id": e.get("id"),
            "name":   tags.get("name", "Parc sans nom"),
            "type":   tags.get("leisure", "park"),
            "lat":    lat,
            "lon":    lon,
        })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["lat", "lon"])
    df = df[df["lat"].between(48.8, 48.92) & df["lon"].between(2.26, 2.42)]
    df["arrondissement"] = None

    df.to_parquet(dest, index=False)
    logger.success(f"    ✓ {len(df)} espaces verts → {dest.name}")


def process_criminalite():
    src  = BRONZE_DIR / "criminalite_paris.csv"
    dest = SILVER_DIR / "criminalite.parquet"
    if not src.exists():
        logger.warning("  Criminalité Bronze absent")
        return

    logger.info("  Silver criminalité…")
    try:
        df = None
        for sep in [";", ","]:
            for enc in ["utf-8", "latin-1", "cp1252"]:
                try:
                    df = pd.read_csv(src, sep=sep, encoding=enc, low_memory=False)
                    if len(df.columns) > 2:
                        break
                except Exception:
                    continue
            if df is not None and len(df.columns) > 2:
                break

        if df is None or df.empty:
            raise ValueError("Fichier illisible")

        df.columns = df.columns.str.lower().str.strip()

        # Colonne arrondissement
        arr_col = next((c for c in df.columns if "arr" in c), None)
        dep_col = next((c for c in df.columns if "dep" in c or "cod" in c), None)

        if arr_col:
            df["arrondissement"] = pd.to_numeric(
                df[arr_col].astype(str).str.extract(r"(\d+)")[0], errors="coerce"
            )
        elif dep_col:
            mask = df[dep_col].astype(str).str.startswith("75")
            df = df[mask].copy()
            df["arrondissement"] = None
        else:
            df["arrondissement"] = None

        # Colonne faits
        faits_col = next(
            (c for c in df.columns if "fait" in c or "nombre" in c or "valeur" in c or "nb" in c),
            df.columns[-1]
        )
        df["nb_faits"] = pd.to_numeric(df[faits_col], errors="coerce")

        df.to_parquet(dest, index=False)
        logger.success(f"    ✓ {len(df)} lignes → {dest.name}")
    except Exception as e:
        logger.error(f"    Erreur criminalité : {e}")


def process_geo():
    src          = BRONZE_DIR / "geo_arrondissements.geojson"
    dest_geojson = SILVER_DIR / "geo_arrondissements.geojson"
    dest_parquet = SILVER_DIR / "geo_arrondissements.parquet"

    if not src.exists():
        logger.warning("  GeoJSON Bronze absent")
        return

    logger.info("  Silver géographie…")
    try:
        gdf = gpd.read_file(src)
        gdf = gdf.to_crs("EPSG:4326")

        # Normalise colonne arrondissement
        arr_col = next(
            (c for c in gdf.columns if c.lower() in ["c_ar", "arr", "arrondissement",
                                                       "numero", "num_arr", "code"]),
            None
        )
        if arr_col:
            gdf["arrondissement"] = pd.to_numeric(
                gdf[arr_col].astype(str).str.extract(r"(\d{1,2})$")[0],
                errors="coerce"
            ).astype("Int64")

        gdf.to_file(dest_geojson, driver="GeoJSON")
        pd.DataFrame(gdf.drop(columns="geometry", errors="ignore")).to_parquet(
            dest_parquet, index=False
        )
        logger.success(f"    ✓ {len(gdf)} arrondissements → {dest_geojson.name}")
    except Exception as e:
        logger.error(f"    Erreur géo : {e}")


def run():
    logger.info("Silver — sources secondaires")
    process_geo()
    process_transports()
    process_education()
    process_parcs()
    process_criminalite()
    logger.success("  ✓ Toutes les sources secondaires traitées")
    return True


if __name__ == "__main__":
    run()