"""
pipeline/silver_commerces_sante.py
Bronze → Silver : Normalise commerces et santé par arrondissement.
Produit : nb_supermarches, nb_pharmacies, nb_boulangeries,
          nb_hopitaux, nb_medecins par arrondissement.
Compétence validée : C2.3
"""
import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, ARRONDISSEMENTS

SRC_COMMERCES = BRONZE_DIR / "commerces_paris.json"
SRC_SANTE     = BRONZE_DIR / "sante_paris.json"
DEST          = SILVER_DIR / "commerces_sante.parquet"

# Mapping OSM amenity/shop → catégorie
SHOP_CATEGORIES = {
    "supermarket": "supermarche",
    "convenience": "supermarche",
    "mall":        "centre_commercial",
    "bakery":      "boulangerie",
    "pharmacy":    "pharmacie",
}
AMENITY_SANTE = {
    "hospital": "hopital",
    "clinic":   "hopital",
    "doctors":  "medecin",
    "dentist":  "dentiste",
}


def parse_osm_elements(elements: list) -> pd.DataFrame:
    """Extrait lat/lon et type depuis les éléments OSM."""
    rows = []
    for e in elements:
        tags   = e.get("tags", {})
        center = e.get("center") or {}
        lat    = center.get("lat") or e.get("lat")
        lon    = center.get("lon") or e.get("lon")
        shop   = tags.get("shop", "")
        amenity = tags.get("amenity", "")
        cat = SHOP_CATEGORIES.get(shop) or AMENITY_SANTE.get(amenity)
        if cat and lat and lon:
            rows.append({"lat": lat, "lon": lon, "categorie": cat,
                         "nom": tags.get("name", "")})
    return pd.DataFrame(rows)


def assign_arrondissement_from_coords(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigne l'arrondissement depuis lat/lon.
    Utilise le GeoJSON Silver si disponible, sinon estimation par bbox.
    """
    geo_path = SILVER_DIR / "geo_arrondissements.geojson"
    if geo_path.exists():
        try:
            import geopandas as gpd
            from shapely.geometry import Point
            gdf = gpd.read_file(geo_path).to_crs("EPSG:4326")
            arr_col = next(
                (c for c in gdf.columns if "arr" in c.lower() or "c_ar" in c.lower()),
                None
            )
            if arr_col:
                gdf["arrondissement"] = pd.to_numeric(
                    gdf[arr_col].astype(str).str.extract(r"(\d{1,2})$")[0],
                    errors="coerce"
                )
                pts = gpd.GeoDataFrame(
                    df, geometry=gpd.points_from_xy(df["lon"], df["lat"]),
                    crs="EPSG:4326"
                )
                joined = gpd.sjoin(pts, gdf[["arrondissement", "geometry"]],
                                   how="left", predicate="within")
                df["arrondissement"] = joined["arrondissement"].values
                return df
        except Exception as e:
            logger.warning(f"  Geo-join impossible ({e}), estimation bbox")

    # Estimation rapide par plage de coordonnées (bbox simplifiée Paris)
    # Chaque arrondissement a une latitude/longitude approximative
    def estimate_arr(lat, lon):
        if not (48.815 < lat < 48.905 and 2.255 < lon < 2.420):
            return None
        # Grille simplifiée (approximation acceptable pour les KPIs)
        if lon < 2.330:
            return 16 if lat > 48.855 else 15
        elif lon < 2.350:
            if lat > 48.880: return 17
            elif lat > 48.860: return 8
            elif lat > 48.840: return 7
            else: return 14
        elif lon < 2.365:
            if lat > 48.875: return 9
            elif lat > 48.855: return 1
            elif lat > 48.835: return 6
            else: return 13
        elif lon < 2.380:
            if lat > 48.875: return 10
            elif lat > 48.855: return 4
            elif lat > 48.835: return 5
            else: return 13
        elif lon < 2.395:
            if lat > 48.875: return 19
            elif lat > 48.860: return 11
            elif lat > 48.840: return 12
            else: return 13
        else:
            if lat > 48.875: return 20
            elif lat > 48.855: return 11
            else: return 12

    df["arrondissement"] = df.apply(
        lambda r: estimate_arr(r["lat"], r["lon"]), axis=1
    )
    return df


def parse_fallback(data: dict, type_data: str) -> pd.DataFrame:
    """Parse les données statiques de repli."""
    rows = []
    arrs = data.get("arrondissements", {})
    for arr_str, vals in arrs.items():
        row = {"arrondissement": int(arr_str)}
        row.update(vals)
        rows.append(row)
    return pd.DataFrame(rows)


def run():
    logger.info("Silver commerces et santé…")

    base = pd.DataFrame({"arrondissement": ARRONDISSEMENTS})

    # ── Commerces ─────────────────────────────────────────────────────────
    if SRC_COMMERCES.exists():
        raw = json.loads(SRC_COMMERCES.read_text())

        if "elements" in raw:
            # Format OSM live
            df_osm = parse_osm_elements(raw["elements"])
            if not df_osm.empty:
                df_osm = assign_arrondissement_from_coords(df_osm)
                df_osm = df_osm.dropna(subset=["arrondissement"])
                df_osm["arrondissement"] = df_osm["arrondissement"].astype(int)

                for cat, col in [
                    ("supermarche",      "nb_supermarches"),
                    ("pharmacie",        "nb_pharmacies"),
                    ("boulangerie",      "nb_boulangeries"),
                    ("centre_commercial","nb_centres_commerciaux"),
                ]:
                    cnt = (
                        df_osm[df_osm["categorie"] == cat]
                        .groupby("arrondissement").size()
                        .reset_index(name=col)
                    )
                    base = base.merge(cnt, on="arrondissement", how="left")
        else:
            # Format statique
            df_static = parse_fallback(raw, "commerces")
            for col in ["supermarches", "pharmacies", "boulangeries", "centres_commerciaux"]:
                src_col = col
                dst_col = f"nb_{col}"
                if src_col in df_static.columns:
                    base = base.merge(
                        df_static[["arrondissement", src_col]].rename(columns={src_col: dst_col}),
                        on="arrondissement", how="left"
                    )
    else:
        logger.warning("  Commerces Bronze absent")

    # ── Santé ──────────────────────────────────────────────────────────────
    if SRC_SANTE.exists():
        raw = json.loads(SRC_SANTE.read_text())

        if "elements" in raw:
            df_osm = parse_osm_elements(raw["elements"])
            if not df_osm.empty:
                df_osm = assign_arrondissement_from_coords(df_osm)
                df_osm = df_osm.dropna(subset=["arrondissement"])
                df_osm["arrondissement"] = df_osm["arrondissement"].astype(int)

                for cat, col in [
                    ("hopital",  "nb_hopitaux"),
                    ("medecin",  "nb_medecins"),
                    ("dentiste", "nb_dentistes"),
                ]:
                    cnt = (
                        df_osm[df_osm["categorie"] == cat]
                        .groupby("arrondissement").size()
                        .reset_index(name=col)
                    )
                    base = base.merge(cnt, on="arrondissement", how="left")
        else:
            df_static = parse_fallback(raw, "sante")
            for col in ["hopitaux", "medecins", "dentistes"]:
                dst_col = f"nb_{col}"
                if col in df_static.columns:
                    base = base.merge(
                        df_static[["arrondissement", col]].rename(columns={col: dst_col}),
                        on="arrondissement", how="left"
                    )
    else:
        logger.warning("  Santé Bronze absent")

    # Remplir NaN par 0
    for col in base.columns:
        if col != "arrondissement":
            base[col] = base[col].fillna(0).astype(int)

    base.to_parquet(DEST, index=False)
    logger.success(f"  ✓ Commerces/santé Silver : {len(base)} arrondissements → {DEST.name}")
    logger.info(f"  Colonnes : {[c for c in base.columns if c != 'arrondissement']}")
    return True


if __name__ == "__main__":
    run()
