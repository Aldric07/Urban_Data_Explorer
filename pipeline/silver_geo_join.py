"""
pipeline/silver_geo_join.py
Enrichit les fichiers Silver avec l'arrondissement via jointure spatiale.
Pour tous les fichiers qui ont lat/lon mais pas d'arrondissement.
Utilise GeoPandas + le GeoJSON des contours Silver.
Compétence validée : C1.3 (enrichissement territorial), C2.3
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SILVER_DIR


GEO_SRC = SILVER_DIR / "geo_arrondissements.geojson"


def load_arrondissements_gdf() -> gpd.GeoDataFrame | None:
    """Charge le GeoDataFrame des arrondissements."""
    if not GEO_SRC.exists():
        logger.warning("  GeoJSON arrondissements absent — jointure spatiale impossible")
        return None
    try:
        gdf = gpd.read_file(GEO_SRC)
        gdf = gdf.to_crs("EPSG:4326")
        # Normalise colonne arrondissement
        arr_col = next(
            (c for c in gdf.columns if "arr" in c.lower() or "c_ar" in c.lower()),
            None
        )
        if arr_col:
            gdf["arrondissement"] = pd.to_numeric(
                gdf[arr_col].astype(str).str.extract(r"(\d{1,2})$")[0],
                errors="coerce"
            ).astype("Int64")
        return gdf[["arrondissement", "geometry"]]
    except Exception as e:
        logger.error(f"  Erreur chargement GeoJSON : {e}")
        return None


def spatial_join_arrondissement(
    df: pd.DataFrame,
    lat_col: str = "lat",
    lon_col: str = "lon",
    gdf_arr: gpd.GeoDataFrame = None
) -> pd.DataFrame:
    """Ajoute la colonne arrondissement par jointure spatiale."""
    if gdf_arr is None:
        return df

    mask = df[lat_col].notna() & df[lon_col].notna()
    if not mask.any():
        return df

    sub = df[mask].copy()
    geometry = gpd.points_from_xy(sub[lon_col], sub[lat_col])
    gdf_pts = gpd.GeoDataFrame(sub, geometry=geometry, crs="EPSG:4326")

    joined = gpd.sjoin(gdf_pts, gdf_arr, how="left", predicate="within")
    arr_map = joined["arrondissement_right"] if "arrondissement_right" in joined.columns \
              else joined["arrondissement"]

    df.loc[mask, "arrondissement"] = arr_map.values
    return df


def enrich_parquet(path: Path, gdf: gpd.GeoDataFrame) -> bool:
    """Relit un Parquet Silver, enrichit avec arrondissement, resauvegarde."""
    try:
        df = pd.read_parquet(path)

        if "arrondissement" in df.columns and df["arrondissement"].notna().mean() > 0.8:
            logger.info(f"  {path.name} : arrondissement déjà présent à >80%, skip")
            return True

        if "lat" not in df.columns or "lon" not in df.columns:
            logger.info(f"  {path.name} : pas de colonnes lat/lon, skip")
            return True

        n_before = df["arrondissement"].notna().sum() if "arrondissement" in df.columns else 0
        df = spatial_join_arrondissement(df, gdf_arr=gdf)
        n_after = df["arrondissement"].notna().sum()

        df.to_parquet(path, index=False)
        logger.success(f"  ✓ {path.name} : {n_before} → {n_after} arrondissements renseignés")
        return True
    except Exception as e:
        logger.error(f"  Erreur {path.name} : {e}")
        return False


def run():
    logger.info("Silver geo-join — enrichissement arrondissement par coordonnées")

    gdf = load_arrondissements_gdf()
    if gdf is None:
        logger.warning("  Pas de GeoJSON disponible, jointure spatiale annulée")
        return False

    # Fichiers Silver à enrichir
    targets = [
        SILVER_DIR / "transports.parquet",
        SILVER_DIR / "parcs.parquet",
        SILVER_DIR / "securite_urbaine.parquet",
    ]

    for path in targets:
        if path.exists():
            enrich_parquet(path, gdf)
        else:
            logger.info(f"  {path.name} absent, skip")

    logger.success("  ✓ Geo-join terminé")
    return True


if __name__ == "__main__":
    run()
