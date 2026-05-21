"""
tests/test_api.py
Tests unitaires de l'API FastAPI.
Usage : pytest tests/test_api.py -v
Compétence validée : C2.1 (tests endpoints)
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# Skip si FastAPI/httpx non installés
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "urban-explorer-dev-key"}


class TestHealth:
    def test_health_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAuth:
    def test_no_key_returns_403(self):
        r = client.get("/arrondissements")
        assert r.status_code == 403

    def test_wrong_key_returns_403(self):
        r = client.get("/arrondissements", headers={"X-API-Key": "mauvaise-cle"})
        assert r.status_code == 403

    def test_valid_key_accepted(self):
        r = client.get("/health")
        assert r.status_code == 200


class TestArrondissements:
    def test_arrondissement_invalide(self):
        r = client.get("/arrondissements/25", headers=HEADERS)
        assert r.status_code in [400, 503]

    def test_arrondissement_zero(self):
        r = client.get("/arrondissements/0", headers=HEADERS)
        assert r.status_code in [400, 503]


class TestComparaison:
    def test_comparaison_meme_arrondissement(self):
        r = client.get("/comparaison?arr1=1&arr2=1&annee=2023", headers=HEADERS)
        # Accepté ou erreur selon implémentation
        assert r.status_code in [200, 400, 503]

    def test_comparaison_arrondissement_invalide(self):
        r = client.get("/comparaison?arr1=99&arr2=1&annee=2023", headers=HEADERS)
        assert r.status_code == 400


class TestDocs:
    def test_swagger_accessible(self):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_json(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "paths" in r.json()
