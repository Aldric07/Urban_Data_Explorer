# Urban Data Explorer

Explorer, comprendre et comparer les dynamiques du logement au cœur de Paris.

## Structure du projet

```
urban-data-explorer/
├── data/
│   ├── bronze/        # Données brutes téléchargées (JSON, CSV originaux)
│   ├── silver/        # Données nettoyées et géocodées (Parquet)
│   └── gold/          # Agrégats prêts à l'emploi par arrondissement (Parquet)
├── ingestion/         # Scripts de collecte des données sources
├── pipeline/          # Transformations Bronze → Silver → Gold
├── api/               # Backend FastAPI
├── dashboard/         # Frontend HTML + MapLibre GL JS
├── tests/             # Tests unitaires et de charge
└── docs/              # Documentation d'architecture
```

## Lancement rapide

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Ingestion des données (Bronze)
python ingestion/run_all.py

# 3. Transformation (Silver → Gold)
python pipeline/run_pipeline.py

# 4. Lancer l'API
uvicorn api.main:app --reload --port 8000

# 5. Ouvrir le dashboard
open dashboard/index.html
```

## Sources de données

| Source | Indicateur | API |
|---|---|---|
| DVF (data.gouv) | Prix immobiliers | fichiers CSV annuels |
| RPLS (data.gouv) | Logements sociaux | fichiers CSV |
| INSEE Filosofi | Revenus par IRIS | fichiers CSV |
| IDFM | Transports (métro/bus) | API GTFS |
| data.education.gouv | Écoles et lycées | API REST |
| FINESS | Santé (hôpitaux, médecins) | fichiers CSV |
| Overpass (OSM) | Parcs, commerces | API REST |
| AIRPARIF | Qualité de l'air | fichiers open data |
| Criminalité | Faits constatés | data.gouv CSV |
| DRIHL | Loyers de référence | fichiers CSV |
| geo.api.gouv.fr | Contours arrondissements | API GeoJSON |
