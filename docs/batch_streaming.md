# Architecture Batch & Streaming — Urban Data Explorer

## Vue d'ensemble

Le projet Urban Data Explorer implémente deux modes de traitement complémentaires :

| Mode | Script | Fréquence | Source | Destination |
|------|--------|-----------|--------|-------------|
| **Batch** | `pipeline/batch_processor.py` | Nuit à 02h00 (APScheduler) | DVF Bronze (CSV.gz) | Gold Parquet + PostgreSQL |
| **Streaming** | `pipeline/streaming_air_quality.py` | Toutes les 30s | AIRPARIF / simulation | MongoDB `stream_events` |

Ces deux pipelines tournent **en parallèle et de façon indépendante** de l'API FastAPI.

---

## 1. Pipeline Batch — Prix/m² DVF

### Rôle

Le batch retraite chaque nuit l'ensemble des fichiers Bronze DVF (transactions immobilières de la Ville de Paris, années 2021–2024) pour recalculer les agrégats Gold et mettre à jour PostgreSQL.

### Flux de données

```
data/bronze/dvf/*.csv.gz
        │
        ▼ silver_dvf.run()
data/silver/dvf/dvf_{année}.parquet
        │
        ▼ gold_agregats.run()
data/gold/agregats_arrondissements.parquet   (prix médian × arrondissement × année)
        │
        ▼ gold_indicateurs.run() + gold_final.run()
data/gold/gold_final.parquet                 (Golden record consolidé)
        │
        ▼ load_postgres (UPSERT)
PostgreSQL : tables prix_median, logement_social, indicateur
```

### Scheduler APScheduler

```python
# Mode daemon : lance automatiquement le batch à 02h00
python3 pipeline/batch_processor.py --schedule
```

APScheduler utilise un `BlockingScheduler` avec un `CronTrigger` configuré sur `hour=2, minute=0, timezone="Europe/Paris"`. La tolérance de retard est fixée à 1 heure (`misfire_grace_time=3600`) pour gérer les redémarrages de machine.

### Rapport de batch

Chaque exécution produit deux fichiers JSON :
- `data/gold/batch_reports/report_{YYYYMMDD_HHMMSS}.json` — rapport horodaté conservé
- `data/gold/batch_reports/last_report.json` — pointeur vers le dernier rapport (lu par l'API)

Structure du rapport :
```json
{
  "batch_id": "20260622_020000",
  "start_time": "2026-06-22T00:00:00+00:00",
  "duration_seconds": 47.3,
  "status": "success",
  "stats": {
    "dvf_bronze_files": 4,
    "gold_rows": 80,
    "arrondissements_covered": 20,
    "nb_transactions_total": 124500,
    "prix_m2_median_paris": 10800.0
  },
  "postgres": { "status": "ok", "rows_updated": { "prix_median": 80, "indicateurs": 200 } },
  "anomalies": [],
  "errors_count": 0
}
```

### Détection d'anomalies

Le batch analyse automatiquement le Gold final et détecte :

| Type | Condition | Sévérité |
|------|-----------|----------|
| `arrondissement_manquant` | Arrondissement absent pour une année donnée | warning |
| `prix_aberrant` | Prix > μ + 3σ ou ≤ 0 | warning / error |
| `valeur_manquante` | NaN dans `prix_m2_median` ou `nb_transactions` | warning |
| `volume_faible` | Moins de 10 transactions (arr, année) | info |

### Commandes disponibles

```bash
# Exécution immédiate (production)
python3 pipeline/batch_processor.py

# Mode simulation (sans écriture PostgreSQL)
python3 pipeline/batch_processor.py --dry-run

# Daemon planifié (nuit à 02h00)
python3 pipeline/batch_processor.py --schedule

# Via Makefile
make batch        # (si ajouté au Makefile)
```

### Endpoint API associé

```
GET /batch/status
```

Retourne le contenu de `last_report.json`. Pas d'authentification requise (dashboard public).

---

## 2. Pipeline Streaming — Qualité de l'air (AIRPARIF)

### Rôle

Le streaming poll l'API AIRPARIF toutes les 30 secondes pour récupérer l'Indice de Qualité de l'Air (IQA) par arrondissement, détecte les alertes de pollution et alimente MongoDB en temps réel.

### Stratégie de source (cascade)

```
1. API AIRPARIF live (si AIRPARIF_API_KEY défini dans l'env)
          │ timeout 5s
          ▼ en cas d'échec
2. Données Bronze qualite_air_paris.json + variation temporelle réaliste
          │
          ▼ toujours disponible
3. Valeurs de référence IQA par arrondissement + bruit gaussien
```

La variation temporelle dans le fallback simule :
- Rush matin (7h–9h) : +20% IQA
- Rush soir (17h–19h) : +18% IQA
- Nuit (0h–5h) : -15% IQA
- Événements ponctuels de pollution (~10% des cycles) : +25 à +50 IQA sur un arrondissement

### Seuils d'alerte (norme française)

| Niveau | Condition | Couleur dashboard |
|--------|-----------|-------------------|
| Normal | IQA ≤ 75 | — |
| **Orange** | 75 < IQA ≤ 100 | Badge orange |
| **Rouge** | IQA > 100 | Badge rouge clignotant |

### Structure du document MongoDB

Collection : `urban_data.stream_events`

```json
{
  "type":          "air_quality",
  "source":        "bronze_fallback",
  "ingested_at":   ISODate("2026-06-22T10:00:00Z"),
  "timestamp":     ISODate("2026-06-22T10:00:00Z"),
  "arrondissement": 8,
  "iqa":           82.4,
  "no2_µg_m3":    46.1,
  "pm25_µg_m3":   18.9,
  "alert_level":   "orange",
  "iqa_24h_mean":  61.2
}
```

L'index TTL sur `ingested_at` purge automatiquement les documents après 7 jours.

### Agrégat glissant 24h

La classe `RollingWindow24h` maintient en mémoire les mesures des dernières 24h par arrondissement (deque avec cutoff timestamp). Elle est consultée à chaque cycle pour enrichir chaque document avec `iqa_24h_mean`.

### Commandes disponibles

```bash
# Streaming continu (Ctrl+C pour arrêter)
python3 pipeline/streaming_air_quality.py

# Un seul cycle (test/debug)
python3 pipeline/streaming_air_quality.py --once

# Intervalle personnalisé
python3 pipeline/streaming_air_quality.py --interval 60

# Avec API AIRPARIF live
AIRPARIF_API_KEY=ma_clé python3 pipeline/streaming_air_quality.py
```

### Endpoint API associé

```
GET /stream/air-quality?hours=24&alert_only=false
```

Paramètres :
- `hours` (1–168) : fenêtre temporelle d'agrégation (défaut 24h)
- `alert_only` : si `true`, retourne uniquement les arrondissements en alerte

Réponse :
```json
{
  "updated_at":    "2026-06-22T10:00:00Z",
  "window_hours":  24,
  "alerts_active": 2,
  "alerts": [
    { "arrondissement": 18, "iqa": 107.3, "alert_level": "rouge", "no2": 54.2 }
  ],
  "readings": [
    { "arrondissement": 1, "iqa_latest": 52.1, "iqa_mean": 49.8, "alert_level": null, ... }
  ]
}
```

---

## 3. Intégration dans le dashboard

### Widget qualité de l'air (sidebar)

- Affiché dans la section "Qualité de l'air" de la sidebar
- Mis à jour toutes les **30 secondes** via `setInterval`
- Affiche un badge rouge/orange dans le titre si des alertes sont actives
- Liste les arrondissements en alerte avec leur IQA

### Marqueurs carte

Lorsque des alertes sont actives, des marqueurs colorés apparaissent sur la carte MapLibre GL JS aux coordonnées centroïdes des arrondissements concernés. Les marqueurs rouges clignotent (animation CSS `@keyframes`).

### Distinction batch vs streaming

| Donnée | Source | Fréquence de mise à jour | Affichage |
|--------|--------|--------------------------|-----------|
| Prix/m² (choroplèthe) | Gold Parquet / PostgreSQL | Chaque nuit (batch) | Carte statique |
| Qualité de l'air | MongoDB stream_events | 30 secondes (streaming) | Marqueurs dynamiques |

Cette distinction visuelle démontre la complémentarité des deux paradigmes de traitement.

---

## 4. Exécution parallèle

Les trois processus cohabitent sans conflit :

```bash
# Terminal 1 — API FastAPI
make api
# → uvicorn api.main:app --reload --port 8000

# Terminal 2 — Streaming air quality (continu)
python3 pipeline/streaming_air_quality.py

# Terminal 3 — Batch scheduler (daemon)
python3 pipeline/batch_processor.py --schedule
# → exécution automatique à 02h00 chaque nuit
```

---

## 5. Compétences RNCP40875 couvertes

| Compétence | Description | Implémentation |
|-----------|-------------|----------------|
| **C2.2** | Traitement par lot (batch) planifiable | `batch_processor.py` + APScheduler |
| **C2.2** | Traitement en flux (streaming) | `streaming_air_quality.py` poll 30s |
| **C1.1** | Base relationnelle PostgreSQL | UPSERT idempotent via SQLAlchemy |
| **C1.2** | Base NoSQL MongoDB | Documents `stream_events`, index TTL |
| **C2.3** | Transformation Bronze→Silver→Gold | Pipeline en cascade + détection anomalies |
| **C2.4** | Logs structurés, traçabilité | loguru + rapport JSON horodaté |

---

## 6. Configuration

Variables d'environnement optionnelles (`.env`) :

```env
# Active l'API AIRPARIF live (sinon simulation réaliste)
AIRPARIF_API_KEY=votre_clé_api

# Remplace les URI par défaut si besoin
POSTGRES_URI=postgresql+psycopg2://urban:urban_dev_pwd@localhost:5433/urban_data
MONGO_URI=mongodb://urban:urban_dev_pwd@localhost:27017/urban_data?authSource=admin
```

---

*Document rédigé pour la soutenance RNCP40875 — Urban Data Explorer, juin 2026.*
