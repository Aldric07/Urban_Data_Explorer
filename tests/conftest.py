"""
tests/conftest.py — Fixtures pytest partagées
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def project_root():
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def gold_dir(project_root):
    return project_root / "data" / "gold"


@pytest.fixture(scope="session")
def silver_dir(project_root):
    return project_root / "data" / "silver"


@pytest.fixture(scope="session")
def bronze_dir(project_root):
    return project_root / "data" / "bronze"
