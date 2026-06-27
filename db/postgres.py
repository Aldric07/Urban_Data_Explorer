"""
db/postgres.py — Schéma relationnel PostgreSQL + PostGIS (C1.1, C1.3, C1.4)

Modèle normalisé en 3NF :
- arrondissement   : référentiel (PK = code 1..20) + géométrie PostGIS (4326)
- transaction_dvf  : transactions immobilières (fait, FK arrondissement)
- prix_median      : prix m² agrégés par (arrondissement, année)
- logement_social  : parc social par (arrondissement, année)
- indicateur       : indicateurs custom multi-thèmes (qualité de vie, accessibilité…)

Contraintes d'intégrité :
- PK / FK explicites (arrondissement_code)
- CHECK sur l'arrondissement (1..20), année (>= 2000), prix > 0
- UNIQUE composites pour empêcher les doublons d'agrégats
- Index spatiaux GIST + index temporels sur année
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from geoalchemy2 import Geometry

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import POSTGRES_URI


class Base(DeclarativeBase):
    pass


# ── Tables ──────────────────────────────────────────────────────────────────

class Arrondissement(Base):
    """Référentiel des 20 arrondissements de Paris + géométrie PostGIS."""
    __tablename__ = "arrondissement"

    code = Column(Integer, primary_key=True)
    nom = Column(String(64), nullable=False)
    surface_km2 = Column(Numeric(10, 4))
    population = Column(Integer)
    geom = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326))

    transactions = relationship("TransactionDVF", back_populates="arrondissement_ref")
    prix = relationship("PrixMedian", back_populates="arrondissement_ref")
    logements_sociaux = relationship("LogementSocial", back_populates="arrondissement_ref")
    indicateurs = relationship("Indicateur", back_populates="arrondissement_ref")

    __table_args__ = (
        CheckConstraint("code BETWEEN 1 AND 20", name="ck_arrondissement_code_range"),
        Index("ix_arrondissement_geom", "geom", postgresql_using="gist"),
    )


class TransactionDVF(Base):
    """Transactions DVF unitaires (source : data.gouv DVF)."""
    __tablename__ = "transaction_dvf"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arrondissement_code = Column(
        Integer, ForeignKey("arrondissement.code", ondelete="CASCADE"), nullable=False
    )
    date_mutation = Column(Date, nullable=False)
    annee = Column(Integer, nullable=False)
    valeur_fonciere = Column(Numeric(14, 2))
    surface_reelle_bati = Column(Numeric(10, 2))
    prix_m2 = Column(Numeric(10, 2))
    type_local = Column(String(32))   # Appartement / Maison / Local
    nb_pieces = Column(Integer)
    adresse = Column(Text)
    geom_point = Column(Geometry(geometry_type="POINT", srid=4326))

    arrondissement_ref = relationship("Arrondissement", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("annee >= 2000", name="ck_dvf_annee"),
        CheckConstraint("prix_m2 IS NULL OR prix_m2 > 0", name="ck_dvf_prix_positif"),
        Index("ix_dvf_arr_annee", "arrondissement_code", "annee"),
        Index("ix_dvf_geom", "geom_point", postgresql_using="gist"),
    )


class PrixMedian(Base):
    """Agrégat prix m² par (arrondissement, année) — alimente le choroplèthe."""
    __tablename__ = "prix_median"

    arrondissement_code = Column(
        Integer, ForeignKey("arrondissement.code", ondelete="CASCADE"), primary_key=True
    )
    annee = Column(Integer, primary_key=True)
    prix_m2_median = Column(Numeric(10, 2))
    prix_m2_moyen = Column(Numeric(10, 2))
    nb_transactions = Column(Integer)
    prix_m2_variation_pct = Column(Numeric(6, 2))

    arrondissement_ref = relationship("Arrondissement", back_populates="prix")

    __table_args__ = (
        CheckConstraint("annee >= 2000", name="ck_prix_annee"),
        CheckConstraint(
            "prix_m2_median IS NULL OR prix_m2_median > 0",
            name="ck_prix_positif",
        ),
        Index("ix_prix_annee", "annee"),
    )


class LogementSocial(Base):
    """Parc social par (arrondissement, année) — source RPLS."""
    __tablename__ = "logement_social"

    arrondissement_code = Column(
        Integer, ForeignKey("arrondissement.code", ondelete="CASCADE"), primary_key=True
    )
    annee = Column(Integer, primary_key=True)
    nb_logements_sociaux = Column(Integer)
    part_logements_sociaux_pct = Column(Numeric(5, 2))

    arrondissement_ref = relationship("Arrondissement", back_populates="logements_sociaux")

    __table_args__ = (
        CheckConstraint("annee >= 2000", name="ck_ls_annee"),
        CheckConstraint(
            "part_logements_sociaux_pct IS NULL OR part_logements_sociaux_pct BETWEEN 0 AND 100",
            name="ck_ls_part_range",
        ),
    )


class Indicateur(Base):
    """Indicateurs custom (qualité de vie, accessibilité, sécurité, économique)."""
    __tablename__ = "indicateur"

    id = Column(Integer, primary_key=True, autoincrement=True)
    arrondissement_code = Column(
        Integer, ForeignKey("arrondissement.code", ondelete="CASCADE"), nullable=False
    )
    nom = Column(String(64), nullable=False)        # ex: 'qualite_air', 'accessibilite_transport'
    categorie = Column(String(32), nullable=False)  # ex: 'qualite_vie', 'accessibilite', 'securite', 'economique'
    valeur = Column(Float)
    unite = Column(String(32))
    annee = Column(Integer)
    source = Column(String(64))
    detail = Column(JSONB)                          # contexte libre (paramètres, sous-mesures)

    arrondissement_ref = relationship("Arrondissement", back_populates="indicateurs")

    __table_args__ = (
        UniqueConstraint(
            "arrondissement_code", "nom", "annee",
            name="uq_indicateur_arr_nom_annee",
        ),
        Index("ix_indicateur_categorie", "categorie"),
    )


# ── Moteur & session ────────────────────────────────────────────────────────

_engine = None
_SessionLocal = None


def get_engine():
    """Singleton du moteur SQLAlchemy. Pool tuné pour FastAPI."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            POSTGRES_URI,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager transactionnel."""
    s = get_sessionmaker()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_schema() -> None:
    """Crée toutes les tables (idempotent). À appeler après que PostGIS soit prêt."""
    engine = get_engine()
    # Active PostGIS si pas déjà fait (le conteneur postgis le fait au démarrage,
    # mais idempotent ici pour usage hors Docker).
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis;")
    Base.metadata.create_all(engine)
