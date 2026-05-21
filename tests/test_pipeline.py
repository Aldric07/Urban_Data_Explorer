"""
tests/test_pipeline.py — Tests qualité données + streaming
Usage : pytest tests/ -v
Compétences validées : C1.4, C2.4
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, GOLD_DIR, ARRONDISSEMENTS


class TestBronze:
    def test_geo_arrondissements_exists(self):
        assert (BRONZE_DIR / "geo_arrondissements.geojson").exists()

    def test_dvf_at_least_one_year(self):
        dvf_dir = BRONZE_DIR / "dvf"
        files = list(dvf_dir.glob("*.csv.gz")) if dvf_dir.exists() else []
        assert len(files) > 0, "Aucun DVF — python ingestion/dvf_prix.py"

    def test_qualite_air_exists(self):
        assert (BRONZE_DIR / "qualite_air_paris.json").exists()


class TestSilverDVF:
    @pytest.fixture
    def df(self):
        p = SILVER_DIR / "dvf" / "dvf_all.parquet"
        if not p.exists(): pytest.skip("DVF Silver absent")
        return pd.read_parquet(p)

    def test_prix_positifs(self, df):
        assert (df["prix_m2"] > 0).all()

    def test_prix_plausibles(self, df):
        assert df["prix_m2"].between(500, 60000).all()

    def test_arrondissements_valides(self, df):
        assert df[~df["arrondissement"].isin(ARRONDISSEMENTS)].empty

    def test_couverture(self, df):
        manquants = set(ARRONDISSEMENTS) - set(df["arrondissement"].unique())
        assert len(manquants) <= 2

    def test_surface_non_nulle(self, df):
        assert (df["surface_reelle_bati"] > 0).all()

    def test_annees_plausibles(self, df):
        assert df["annee"].between(2015, 2025).all()


class TestSilverTransports:
    @pytest.fixture
    def df(self):
        p = SILVER_DIR / "transports.parquet"
        if not p.exists(): pytest.skip()
        return pd.read_parquet(p)

    def test_coordonnees_paris(self, df):
        v = df.dropna(subset=["lat", "lon"])
        assert v["lat"].between(48.8, 48.92).all()
        assert v["lon"].between(2.26, 2.42).all()


class TestSilverQualiteAir:
    @pytest.fixture
    def df(self):
        p = SILVER_DIR / "qualite_air.parquet"
        if not p.exists(): pytest.skip()
        return pd.read_parquet(p)

    def test_20_arrondissements(self, df):
        assert len(df) == 20

    def test_iqa_plausible(self, df):
        if "iqa_moyen" in df.columns:
            assert df["iqa_moyen"].between(0, 100).all()


class TestGoldAgregats:
    @pytest.fixture
    def df(self):
        p = GOLD_DIR / "agregats_arrondissements.parquet"
        if not p.exists(): pytest.skip()
        return pd.read_parquet(p)

    def test_tous_arrondissements(self, df):
        manquants = set(ARRONDISSEMENTS) - set(df["arrondissement"].unique())
        assert len(manquants) == 0

    def test_colonnes_requises(self, df):
        for c in ["arrondissement", "annee", "prix_m2_median", "nb_transactions"]:
            assert c in df.columns

    def test_variation_bornee(self, df):
        if "prix_m2_variation_pct" in df.columns:
            assert df["prix_m2_variation_pct"].dropna().between(-50, 100).all()


class TestGoldIndicateurs:
    @pytest.fixture
    def df(self):
        p = GOLD_DIR / "indicateurs_custom.parquet"
        if not p.exists(): pytest.skip()
        return pd.read_parquet(p)

    def test_20_arrondissements(self, df):
        assert len(df) == 20

    def test_4_indicateurs(self, df):
        for c in ["score_accessibilite", "score_qualite_vie",
                  "score_securite", "score_accessibilite_immo"]:
            assert c in df.columns

    def test_scores_0_10(self, df):
        for c in [col for col in df.columns if col.startswith("score_")]:
            assert df[c].between(0, 10).all()

    def test_score_global(self, df):
        assert "score_global" in df.columns


class TestGoldFinal:
    @pytest.fixture
    def df(self):
        p = GOLD_DIR / "gold_final.parquet"
        if not p.exists(): pytest.skip()
        return pd.read_parquet(p)

    def test_colonnes_minimales(self, df):
        for c in ["arrondissement", "annee", "prix_m2_median"]:
            assert c in df.columns

    def test_no_nulls_cles(self, df):
        assert df["arrondissement"].notna().all()
        assert df["annee"].notna().all()

    def test_couverture_annees(self, df):
        assert len(df["annee"].unique()) >= 3


class TestStreaming:
    def test_stream_dir_creatable(self):
        (GOLD_DIR / "stream").mkdir(exist_ok=True)
        assert (GOLD_DIR / "stream").exists()

    def test_consolidated_si_present(self):
        p = GOLD_DIR / "stream_consolidated.parquet"
        if not p.exists(): pytest.skip("Streaming non encore lancé")
        df = pd.read_parquet(p)
        assert "arrondissement" in df.columns
        assert "prix_m2_median_stream" in df.columns
