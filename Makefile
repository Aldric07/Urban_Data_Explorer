# Makefile — Urban Data Explorer
# Usage : make <cible>

PYTHON = venv/bin/python3
PIP    = venv/bin/pip

.PHONY: install ingest pipeline stream stream-continuous check test test-coverage \
        api docker-build docker-up docker-down db-up db-down db-ui db-logs \
        load-postgres load-mongo load-db all all-db clean clean-silver clean-gold help

# ── Setup ────────────────────────────────────────────────────────────────────
venv:
	python3 -m venv venv
	@echo "✓ Environnement virtuel créé"

install: venv
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements.txt
	@echo "✓ Dépendances installées dans venv/"

# ── Étape 1 : Ingestion Bronze ───────────────────────────────────────────────
ingest:
	$(PYTHON) ingestion/run_all.py

# ── Étape 2 : Pipeline Silver → Gold ────────────────────────────────────────
pipeline:
	$(PYTHON) pipeline/run_pipeline.py

# ── Streaming micro-batch (démo 20 batchs) ──────────────────────────────────
stream:
	$(PYTHON) pipeline/streaming_microbatch.py --batches 20 --interval 1

stream-continuous:
	$(PYTHON) pipeline/streaming_microbatch.py --continuous --interval 30

# ── Vérification Data Lake ───────────────────────────────────────────────────
check:
	$(PYTHON) pipeline/check_datalake.py

# ── Tests ────────────────────────────────────────────────────────────────────
test:
	venv/bin/pytest tests/ -v

test-coverage:
	venv/bin/pytest tests/ --cov=pipeline --cov=ingestion --cov-report=term-missing

# ── API (hors Docker) ────────────────────────────────────────────────────────
api:
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# ── Docker ───────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

# ── Bases de données ─────────────────────────────────────────────────────────
# Lance uniquement Postgres + Mongo (utile en dev avant `make api`)
db-up:
	docker compose up -d postgres mongo
	@echo "✓ PostgreSQL (localhost:5433) et MongoDB (localhost:27017) démarrés"

# Lance aussi les UI web
db-ui:
	docker compose up -d postgres mongo adminer mongo-express
	@echo "✓ DB + UIs prêtes :"
	@echo "  • Adminer       → http://localhost:8080   (PG | Serveur=postgres | User=urban | Pwd=urban_dev_pwd | Base=urban_data)"
	@echo "  • mongo-express → http://localhost:8081   (login : urban-admin / urban_dev_pwd)"

db-down:
	docker compose stop postgres mongo adminer mongo-express

db-logs:
	docker compose logs -f postgres mongo

# Charge Gold → PostgreSQL + PostGIS
load-postgres:
	$(PYTHON) pipeline/load_postgres.py

# Charge Bronze + catalogue + stream → MongoDB
load-mongo:
	$(PYTHON) pipeline/load_mongo.py

# Charge les deux bases
load-db: load-postgres load-mongo
	@echo "✓ PostgreSQL + MongoDB alimentés"

# ── Pipeline complet en une commande ─────────────────────────────────────────
# Pipeline sans DB (local, sans Docker)
all: install ingest pipeline check
	@echo ""
	@echo "✓ Pipeline complet terminé"
	@echo "→ Charger les DB : make db-up && make load-db"
	@echo "→ Lancer l'API  : make api"

# Pipeline complet AVEC bases de données (nécessite docker compose up -d déjà lancé)
all-db: install ingest pipeline load-db check
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
	@echo "  make install           Crée le venv et installe les dépendances"
	@echo "  make ingest            Télécharge toutes les sources (Bronze)"
	@echo "  make pipeline          Transforme Bronze → Silver → Gold"
	@echo "  make stream            Lance le micro-batch streaming (démo 20 batchs)"
	@echo "  make stream-continuous Streaming continu AIRPARIF (intervalle 30s)"
	@echo "  make check             Vérifie l'état du Data Lake (tailles, lignes)"
	@echo "  make test              Lance les tests pytest"
	@echo "  make test-coverage     pytest avec rapport de couverture"
	@echo "  make api               Démarre l'API FastAPI hors Docker (port 8000)"
	@echo "  make docker-up         Lance tous les 6 services Docker"
	@echo "  make docker-down       Arrête tous les services Docker"
	@echo "  make db-up             Lance uniquement PostgreSQL + MongoDB"
	@echo "  make db-ui             Lance DB + Adminer + mongo-express"
	@echo "  make load-postgres     Charge Gold → PostgreSQL + PostGIS"
	@echo "  make load-mongo        Charge Bronze + catalogue → MongoDB"
	@echo "  make load-db           Charge PostgreSQL ET MongoDB"
	@echo "  make all               install + ingest + pipeline + check"
	@echo "  make all-db            install + ingest + pipeline + load-db + check"
	@echo "  make clean             Supprime les données Silver et Gold"
	@echo ""
