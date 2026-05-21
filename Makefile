# Makefile — Urban Data Explorer
# Usage : make <cible>

.PHONY: install ingest pipeline stream test check api docker clean help

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

# ── Pipeline complet en une commande ─────────────────────────────────────────
all: install ingest pipeline check test
	@echo ""
	@echo "✓ Pipeline complet terminé"
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
	@echo "  make all             Pipeline complet (install+ingest+pipeline+test)"
	@echo "  make clean           Supprime les données Silver et Gold"
	@echo ""
