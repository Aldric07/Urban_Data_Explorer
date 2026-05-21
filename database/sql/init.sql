-- database/sql/init.sql
-- Initialisation PostgreSQL + PostGIS — Urban Data Explorer
-- Compétence validée : C1.1 (base de données relationnelle)

-- Extension spatiale PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ══════════════════════════════════════════════════════════════════════
-- TABLE 1 : arrondissements (référentiel géographique)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS arrondissements (
    id               SERIAL PRIMARY KEY,
    numero           INTEGER NOT NULL UNIQUE CHECK (numero BETWEEN 1 AND 20),
    nom              VARCHAR(100),
    code_postal      CHAR(5),
    superficie_km2   NUMERIC(6,3),
    population_2022  INTEGER,
    geom             GEOMETRY(MULTIPOLYGON, 4326),   -- PostGIS : contours
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arr_numero ON arrondissements(numero);
CREATE INDEX IF NOT EXISTS idx_arr_geom   ON arrondissements USING GIST(geom);

-- ══════════════════════════════════════════════════════════════════════
-- TABLE 2 : prix_immobiliers (données DVF agrégées par arrondissement × année)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS prix_immobiliers (
    id                      SERIAL PRIMARY KEY,
    arrondissement_id       INTEGER REFERENCES arrondissements(numero),
    annee                   INTEGER NOT NULL CHECK (annee BETWEEN 2015 AND 2030),
    prix_m2_median          NUMERIC(10,2),
    prix_m2_moyen           NUMERIC(10,2),
    nb_transactions         INTEGER,
    surface_mediane         NUMERIC(8,2),
    nb_appartements         INTEGER DEFAULT 0,
    nb_maisons              INTEGER DEFAULT 0,
    prix_m2_variation_pct   NUMERIC(6,2),
    created_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE(arrondissement_id, annee)
);

CREATE INDEX IF NOT EXISTS idx_prix_arr  ON prix_immobiliers(arrondissement_id);
CREATE INDEX IF NOT EXISTS idx_prix_year ON prix_immobiliers(annee);
CREATE INDEX IF NOT EXISTS idx_prix_arr_year ON prix_immobiliers(arrondissement_id, annee);

-- ══════════════════════════════════════════════════════════════════════
-- TABLE 3 : logements_sociaux (RPLS par arrondissement)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS logements_sociaux (
    id                          SERIAL PRIMARY KEY,
    arrondissement_id           INTEGER REFERENCES arrondissements(numero),
    annee                       INTEGER NOT NULL,
    nb_logements_sociaux        INTEGER,
    part_logements_sociaux_pct  NUMERIC(5,2),
    created_at                  TIMESTAMP DEFAULT NOW(),
    UNIQUE(arrondissement_id, annee)
);

CREATE INDEX IF NOT EXISTS idx_ls_arr ON logements_sociaux(arrondissement_id);

-- ══════════════════════════════════════════════════════════════════════
-- TABLE 4 : revenus (INSEE Filosofi par arrondissement)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS revenus (
    id               SERIAL PRIMARY KEY,
    arrondissement_id INTEGER REFERENCES arrondissements(numero),
    annee            INTEGER NOT NULL,
    revenu_median    NUMERIC(10,2),
    taux_pauvrete    NUMERIC(5,3),
    created_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE(arrondissement_id, annee)
);

-- ══════════════════════════════════════════════════════════════════════
-- TABLE 5 : loyers_reference (DRIHL encadrement des loyers)
-- ══════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS loyers_reference (
    id                  SERIAL PRIMARY KEY,
    arrondissement_id   INTEGER REFERENCES arrondissements(numero),
    annee               INTEGER NOT NULL,
    loyer_ref_median    NUMERIC(8,2),
    loyer_ref_majore    NUMERIC(8,2),
    loyer_ref_minore    NUMERIC(8,2),
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ══════════════════════════════════════════════════════════════════════
-- VUE : tableau de bord complet par arrondissement × année
-- Utilisée directement par l'API FastAPI
-- ══════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW vue_tableau_bord AS
SELECT
    a.numero                            AS arrondissement,
    p.annee,
    p.prix_m2_median,
    p.prix_m2_moyen,
    p.nb_transactions,
    p.surface_mediane,
    p.prix_m2_variation_pct,
    ls.nb_logements_sociaux,
    ls.part_logements_sociaux_pct,
    r.revenu_median,
    r.taux_pauvrete,
    -- Tension immobilière calculée
    CASE
        WHEN p.prix_m2_median > 0 AND r.revenu_median > 0
        THEN ROUND(r.revenu_median / p.prix_m2_median, 2)
        ELSE NULL
    END AS m2_par_revenu_annuel,
    CASE
        WHEN p.prix_m2_median > 0 AND r.revenu_median > 0
        THEN ROUND((p.prix_m2_median * 50) / r.revenu_median, 1)
        ELSE NULL
    END AS annees_pour_50m2,
    lo.loyer_ref_median
FROM arrondissements a
LEFT JOIN prix_immobiliers p  ON p.arrondissement_id = a.numero
LEFT JOIN logements_sociaux ls ON ls.arrondissement_id = a.numero AND ls.annee = p.annee
LEFT JOIN revenus r           ON r.arrondissement_id = a.numero
LEFT JOIN loyers_reference lo ON lo.arrondissement_id = a.numero AND lo.annee = p.annee
ORDER BY a.numero, p.annee;

-- ══════════════════════════════════════════════════════════════════════
-- Données de référence arrondissements (population INSEE 2022)
-- ══════════════════════════════════════════════════════════════════════
INSERT INTO arrondissements (numero, nom, code_postal, superficie_km2, population_2022)
VALUES
    (1,  '1er arrondissement',  '75001', 1.83,  16266),
    (2,  '2e arrondissement',   '75002', 0.99,  21977),
    (3,  '3e arrondissement',   '75003', 1.17,  35991),
    (4,  '4e arrondissement',   '75004', 1.60,  30675),
    (5,  '5e arrondissement',   '75005', 2.54,  61594),
    (6,  '6e arrondissement',   '75006', 2.15,  43222),
    (7,  '7e arrondissement',   '75007', 4.09,  52000),
    (8,  '8e arrondissement',   '75008', 3.88,  36808),
    (9,  '9e arrondissement',   '75009', 2.18,  60576),
    (10, '10e arrondissement',  '75010', 2.89,  92338),
    (11, '11e arrondissement',  '75011', 3.66, 151082),
    (12, '12e arrondissement',  '75012', 6.38, 141494),
    (13, '13e arrondissement',  '75013', 7.15, 183977),
    (14, '14e arrondissement',  '75014', 5.64, 137966),
    (15, '15e arrondissement',  '75015', 8.50, 241284),
    (16, '16e arrondissement',  '75016', 16.31,166361),
    (17, '17e arrondissement',  '75017', 5.67, 168454),
    (18, '18e arrondissement',  '75018', 6.01, 197820),
    (19, '19e arrondissement',  '75019', 6.79, 191634),
    (20, '20e arrondissement',  '75020', 5.98, 195814)
ON CONFLICT (numero) DO NOTHING;