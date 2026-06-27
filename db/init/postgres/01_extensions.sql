-- Exécuté automatiquement au premier démarrage du conteneur postgres.
-- L'image postgis/postgis active déjà PostGIS sur la base par défaut, mais on
-- s'assure ici qu'elle est bien présente sur urban_data (idempotent).

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- pg_trgm : recherche textuelle sur les adresses
CREATE EXTENSION IF NOT EXISTS pg_trgm;
