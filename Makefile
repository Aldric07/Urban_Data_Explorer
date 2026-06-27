# Makefile — Urban Data Explorer
# Usage : make <cible>

.PHONY: install ingest pipeline stream test check api docker clean help \
        db-up db-down db-logs load-postgres load-mongo load-db

# ── Setup ────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	@echo "✓ Dépendances installées"

# ── Étape 1 : Ingestion Bronze ───────────────────────────────────────────────
ingest:
	python ingestion/run_all.py

# ── Étape 2 : Pipeline Silver → Gold ────────────────────────────────────────
pipeline:
	python pipeline/run_pipeline.py

# ── Streaming micro-batch (démo 10 batchs) ──────────────────────────────────
stream:
	python pipeline/streaming_microbatch.py --batches 20 --interval 1

stream-continuous:
	python pipeline/streaming_microbatch.py --continuous --interval 30

# ── Vérification Data Lake ───────────────────────────────────────────────────
check:
	python pipeline/check_datalake.py

# ── Tests ────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-coverage:
	pytest tests/ --cov=pipeline --cov=ingestion --cov-report=term-missing

# ── API ──────────────────────────────────────────────────────────────────────
api:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# ── Docker ───────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

# ── Bases de données (BC1) ──────────────────────────────────────────────────
# Lance uniquement Postgres + Mongo (utile en dev avant `make api`).
db-up:
	docker compose up -d postgres mongo
	@echo "✓ PostgreSQL (localhost:5433) et MongoDB (localhost:27017) démarrés"

# Lance aussi les UI web (Adminer pour PG, mongo-express pour Mongo)
db-ui:
	docker compose up -d postgres mongo adminer mongo-express
	@echo "✓ DB + UIs prêtes :"
	@echo "  • Adminer       → http://localhost:8080   (PG | postgres | urban | urban_dev_pwd | urban_data)"
	@echo "  • mongo-express → http://localhost:8081   (login : urban-admin / urban_dev_pwd)"

db-down:
	docker compose stop postgres mongo

db-logs:
	docker compose logs -f postgres mongo

# Charge Gold → Postgres
load-postgres:
	python pipeline/load_postgres.py

# Charge Bronze + catalogue + stream → Mongo
load-mongo:
	python pipeline/load_mongo.py

# Charge les deux bases
load-db: load-postgres load-mongo
	@echo "✓ Postgres + Mongo alimentés"

# ── Pipeline complet en une commande ─────────────────────────────────────────
all: install ingest pipeline check test
	@echo ""
	@echo "✓ Pipeline complet terminé"
	@echo "→ Lancer l'API : make api"

# Pipeline complet AVEC bases de données (suppose db-up déjà fait)
all-db: install ingest pipeline load-db check test
	@echo ""
	@echo "✓ Pipeline + DB terminés"
	@echo "→ Lancer l'API : make api"

# ── Nettoyage ────────────────────────────────────────────────────────────────
clean-silver:
	rm -rf data/silver/
	@echo "✓ Silver supprimé"

clean-gold:
	rm -rf data/gold/
	@echo "✓ Gold supprimé"

clean: clean-silver clean-gold
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Nettoyage terminé"

# ── Aide ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Urban Data Explorer — Commandes disponibles"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make install         Installe les dépendances Python"
	@echo "  make ingest          Télécharge toutes les sources (Bronze)"
	@echo "  make pipeline        Transforme Bronze → Silver → Gold"
	@echo "  make stream          Lance le micro-batch streaming (démo)"
	@echo "  make check           Vérifie l'état du Data Lake"
	@echo "  make test            Lance les tests pytest"
	@echo "  make api             Démarre l'API FastAPI (port 8000)"
	@echo "  make docker-up       Lance tout via Docker Compose"
	@echo "  make db-up           Lance uniquement PostgreSQL + MongoDB"
	@echo "  make load-postgres   Charge Gold → PostgreSQL+PostGIS"
	@echo "  make load-mongo      Charge Bronze + catalogue → MongoDB"
	@echo "  make load-db         Charge Postgres ET Mongo"
	@echo "  make all             Pipeline complet (install+ingest+pipeline+test)"
	@echo "  make all-db          Pipeline complet + chargement des DB"
	@echo "  make clean           Supprime les données Silver et Gold"
	@echo ""
