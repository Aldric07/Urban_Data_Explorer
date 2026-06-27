# Urban Data Explorer — Rapport technique du pipeline de données

---

## 1. Présentation du projet

Urban Data Explorer est un projet d'analyse urbaine de Paris. L'objectif est de collecter des données publiques sur les 20 arrondissements parisiens, de les transformer en indicateurs composites, et de les exposer via une API et un dashboard interactif.

Le pipeline suit une architecture **Bronze / Silver / Gold** inspirée du modèle Medallion, avec deux bases de données complémentaires : **MongoDB** pour le brut et **PostgreSQL** pour le structuré.

---

## 2. Les sources de données collectées (14 sources)

| Source | Fournisseur | Format |
|--------|-------------|--------|
| Transactions immobilières (DVF) | DGFiP / data.gouv.fr | CSV.gz par année (2021–2024) |
| Arrêts de transport (métro, RER, bus) | Île-de-France Mobilités | JSON |
| Établissements scolaires | Ministère de l'Éducation nationale | JSON |
| Commerces (supermarchés, pharmacies, boulangeries) | OpenStreetMap Overpass | JSON |
| Établissements de santé (hôpitaux, médecins) | OpenStreetMap Overpass | JSON |
| Parcs et espaces verts | OpenStreetMap Overpass | JSON |
| Qualité de l'air (IQA, NO2, PM2.5) | AIRPARIF | JSON |
| Bruit urbain (indicateur Lden) | BRUITPARIF | JSON |
| Trafic routier (TMJA) | Paris Open Data | JSON |
| Criminalité (faits constatés) | SSMSI / Ministère de l'Intérieur | CSV |
| Commissariats de police | OpenStreetMap Overpass / Préfecture de Police | JSON |
| Casernes de pompiers (BSPP) | OpenStreetMap Overpass / Brigade Sapeurs-Pompiers de Paris | JSON |
| Revenus médians | INSEE Filosofi | ZIP/CSV |
| Loyers de référence | DRIHL / OpenData Paris | CSV |
| Contours géographiques | OpenData Paris | GeoJSON |

---

## 3. Architecture du pipeline — Bronze / Silver / Gold

### 3.1 Couche Bronze — Collecte brute

**Rôle :** Récupérer les données telles quelles depuis les APIs publiques et les sauvegarder dans `data/bronze/` sans aucune transformation.

Chaque script d'ingestion suit le même principe en 3 niveaux de robustesse :

```
Niveau 1 → Appel API live (données fraîches en temps réel)
     ↓ si échec
Niveau 2 → URL de secours (endpoint alternatif)
     ↓ si échec
Niveau 3 → Données statiques intégrées (sources officielles publiées documentées)
```

Un mécanisme de **cache** évite de re-télécharger un fichier déjà présent : si le fichier existe dans `data/bronze/`, le script affiche `"déjà présent, skip"` et passe à la suite.

**Exemple — Qualité de l'air :**
- Tentative 1 : API live AIRPARIF (`magellan.airparif.asso.fr`)
- Si indisponible → données statiques 2023 intégrées dans le code (IQA par arrondissement issu des rapports AIRPARIF publiés)

**Exemple — Criminalité :**
- Tentative 1 : Base communale SSMSI (plus précise)
- Tentative 2 : Base départementale SSMSI
- Si indisponible → CSV généré avec les faits constatés SSMSI 2022 par arrondissement

**Exemple — Sécurité urbaine :**
- Tentative 1 : API Overpass OSM pour `amenity=police` et `amenity=fire_station`
- Tentative 2 : Serveur Overpass de secours (`overpass.kumi.systems`)
- Si indisponible → données statiques intégrées : 30 commissariats (Préfecture de Police) + 25 casernes (BSPP)

**Résultat :** 15 fichiers bruts dans `data/bronze/` (JSON, CSV, GeoJSON)

---

### 3.2 Couche Silver — Nettoyage et normalisation

**Rôle :** Lire les fichiers Bronze, les nettoyer, les standardiser, et les sauvegarder en **format Parquet** dans `data/silver/`.

Un fichier Parquet par thème est produit : `transports.parquet`, `dvf/dvf_all.parquet`, `qualite_air.parquet`, `securite_urbaine.parquet`, etc.

#### Exemple détaillé — Silver DVF (transactions immobilières)

Les données DVF brutes contiennent toutes les ventes de France avec des valeurs aberrantes. Les transformations appliquées sont :

| Étape | Opération | Justification |
|-------|-----------|---------------|
| Filtre géographique | Garde uniquement les codes postaux `750XX` | Restreindre à Paris |
| Filtre nature | Uniquement les `Vente` d'`Appartement` ou `Maison` | Exclure les locaux commerciaux |
| Nettoyage | Suppression des lignes sans prix ni surface | Données incomplètes inutilisables |
| Filtre aberrants | Surface > 5 m², prix > 1 000 €, prix/m² entre 1 000 € et 50 000 € | Éliminer les erreurs de saisie |
| Calcul prix/m² | `prix_m2 = valeur_fonciere / surface_reelle_bati` | Variable clé pour les agrégats |
| Extraction arrondissement | `75001 → 1`, `75020 → 20` | Permettre les groupements |

#### Exemple — Silver Qualité de l'air

L'IQA (Indice de Qualité de l'Air) va de 0 (excellent) à 100 (mauvais). On calcule un score inversé :

```
score_air = 100 - IQA
```

Un IQA de 75 dans le 8e arrondissement donne un `score_air` de 25 — mauvaise qualité d'air.
Un IQA de 52 dans le 16e arrondissement donne un `score_air` de 48 — meilleure qualité d'air.

#### Exemple — Silver Sécurité urbaine

Les fichiers Bronze `commissariats_paris.json` et `pompiers_paris.json` (format OSM Overpass) sont fusionnés en un seul fichier Silver :

| Étape | Opération |
|-------|-----------|
| Fusion | Commissariats + casernes réunis dans `securite_urbaine.parquet` |
| Typage | Colonne `type` : valeur `"commissariats"` ou `"pompiers"` |
| Filtre spatial | Garde uniquement les points dans la bbox de Paris (lat 48.80–48.92, lon 2.25–2.42) |
| Arrondissement | Assigné par jointure spatiale GPS via `silver_geo_join.py` (GeoPandas) |

---

### 3.3 Couche Gold — Agrégations et indicateurs composites

**Rôle :** Produire les données finales agrégées par arrondissement, prêtes pour l'API et le dashboard.

#### Agrégats immobiliers (par arrondissement et par année)

À partir des données Silver DVF, on calcule par couple `(arrondissement, année)` :

| Agrégat | Calcul |
|---------|--------|
| `prix_m2_median` | Médiane du prix au m² |
| `prix_m2_moyen` | Moyenne du prix au m² |
| `nb_transactions` | Nombre de ventes |
| `surface_mediane` | Médiane de la surface en m² |
| `prix_m2_variation_pct` | Variation en % par rapport à l'année précédente |

---

## 4. Les 4 indicateurs composites

### Principe de normalisation commun

Toutes les valeurs brutes sont ramenées sur une **échelle de 0 à 10** via la formule :

```
score = (valeur - min) / (max - min) × 10
```

Pour les indicateurs négatifs (crime, pollution, bruit, congestion), on **inverse** :

```
score = 10 - [(valeur - min) / (max - min) × 10]
```

Ainsi, plus la criminalité est élevée, plus le score sécurité est bas. Plus le bruit est fort, plus le score qualité de vie est bas.

---

### Indicateur I1 — Accessibilité Urbaine

**Objectif :** Mesurer dans quelle mesure les habitants peuvent accéder aux services essentiels à pied ou en transport.

**Formule :**

```
score_accessibilite =
    score_transport   × 40 %
  + score_commerces   × 20 %
  + score_ecoles      × 15 %
  + score_sante       × 15 %
  + centralite        × 10 %
```

**Détail des composantes :**

| Composante | Données source | Calcul intermédiaire |
|------------|---------------|----------------------|
| Transport (40%) | Arrêts IDFM | Comptage des arrêts par arrondissement → normalisation |
| Commerces (20%) | OSM Overpass | Somme supermarchés + pharmacies + boulangeries → normalisation |
| Écoles (15%) | Éducation nationale | Comptage des établissements scolaires → normalisation |
| Santé (15%) | OSM Overpass | Somme hôpitaux + médecins → normalisation |
| Centralité (10%) | Score fixe | 1er = 10, 2e = 9.5, ..., 19e = 5.5, 20e = 6 |

La centralité est un score fixe qui reflète la position géographique dans Paris : les arrondissements du centre ont un accès naturellement plus facile aux services que ceux de la périphérie.

---

### Indicateur I2 — Qualité de Vie

**Objectif :** Mesurer le confort de vie au quotidien en termes d'environnement.

**Formule :**

```
score_qualite_vie =
    score_parcs       × 30 %
  + score_air         × 25 %
  + score_bruit       × 25 %
  + score_circulation × 20 %
```

**Détail des composantes :**

| Composante | Données source | Calcul intermédiaire |
|------------|---------------|----------------------|
| Parcs (30%) | OSM Overpass | Comptage des parcs et jardins → normalisation |
| Qualité air (25%) | AIRPARIF | `score_air = 100 - IQA`, ramené sur 0-10 |
| Bruit (25%) | BRUITPARIF | Indicateur Lden (dB), score inversé fourni directement |
| Circulation (20%) | Paris Open Data / DRIEA | Score de fluidité inversé par rapport au TMJA |

**Exemples de résultats :**
- 8e arrondissement : air pollué (IQA 75), très bruyant (70 dB), trafic dense (32 000 véh./jour) → score qualité de vie faible
- 16e arrondissement : air pur (IQA 52), calme (63 dB), trafic modéré (15 000 véh./jour) → score qualité de vie élevé

---

### Indicateur I3 — Sécurité

**Objectif :** Mesurer le niveau de sécurité d'un arrondissement en combinant la délinquance réelle, la présence policière et la couverture des secours d'urgence.

**Formule :**

```
score_securite =
    score_criminalite     × 60 %
  + score_commissariats   × 25 %
  + score_pompiers        × 15 %
```

**Détail des composantes :**

| Composante | Données source | Calcul | Sens |
|------------|---------------|--------|------|
| Criminalité (60%) | SSMSI / Ministère de l'Intérieur | Somme des faits constatés → normalisation **inverse** | Plus de crimes = score plus bas |
| Commissariats (25%) | OpenStreetMap / Préfecture de Police | Comptage des postes de police par arrondissement → normalisation directe | Plus de commissariats = score plus élevé |
| Pompiers (15%) | OpenStreetMap / BSPP | Comptage des casernes de pompiers par arrondissement → normalisation directe | Plus de casernes = score plus élevé |

**Justification des poids :**
- La criminalité reste le facteur dominant (60%) car elle mesure la dangerosité réelle vécue par les habitants.
- La présence de commissariats (25%) a un effet dissuasif prouvé et assure une réponse rapide aux incidents.
- Les casernes de pompiers (15%) garantissent une intervention d'urgence rapide en cas d'incendie ou d'accident.

**Exemples de résultats :**

| Arrondissement | Faits constatés | Commissariats | Casernes pompiers | Score sécurité |
|---------------|-----------------|---------------|-------------------|---------------|
| 7e | 1 200 (min Paris) | 1 | 1 | ~8.5/10 |
| 8e | 5 800 (max Paris) | 1 | 1 | ~2.0/10 |
| 15e | 2 900 | 2 | 3 (max Paris) | ~6.5/10 |
| 18e | 5 100 | 2 | 2 | ~2.5/10 |
| 5e | 1 500 | 1 | 1 | ~7.8/10 |

---

### Indicateur I4 — Tension Immobilière

**Objectif :** Mesurer si un habitant peut se loger avec son revenu dans cet arrondissement.

**Formule :**

```
score_accessibilite_immo =
    s_achat   × 60 %
  + s_effort  × 40 %
```

**Composante 1 — Pouvoir d'achat immobilier (60%) :**

```
m2_par_revenu = revenu_median / prix_m2_median
```

Représente le nombre de m² que l'on peut acheter avec un an de revenu médian.

| Arrondissement | Revenu médian | Prix/m² | m² achetables |
|---------------|---------------|---------|--------------|
| 16e | 55 000 € | 12 000 €/m² | 4.6 m² |
| 6e | 42 000 € | 15 000 €/m² | 2.8 m² |
| 19e | 24 000 € | 9 000 €/m² | 2.7 m² |

**Composante 2 — Effort locatif (40%) :**

```
effort_locatif = (loyer_ref_m2 × 50) / (revenu_median / 12)
```

Représente la part du salaire mensuel nécessaire pour louer un appartement de 50 m².

| Arrondissement | Loyer 50m²/mois | Salaire mensuel | Effort locatif |
|---------------|----------------|-----------------|---------------|
| 6e | 1 560 € | 3 500 € | 44 % |
| 19e | 1 120 € | 2 000 € | 56 % |

Le score est inversé : moins l'effort est important, meilleur est le score.

---

### Score Global

```
score_global = (I1 + I2 + I3 + I4) / 4
```

Moyenne arithmétique des 4 indicateurs. Chaque dimension compte pour 25 % du score final.

---

## 5. Stockage des données — PostgreSQL et MongoDB

### 5.1 PostgreSQL + PostGIS — La couche analytique

PostgreSQL stocke uniquement la **couche Gold** (données propres, structurées, agrégées).

**Pourquoi PostgreSQL ?**
- Les données Gold ont un schéma **stable et connu** → modèle relationnel adapté
- L'API FastAPI exécute des **requêtes filtrables** : `WHERE arrondissement = 11 AND annee = 2023`
- L'extension **PostGIS** permet des requêtes géospatiales : trouver toutes les transactions dans un polygone
- Les **UPSERT** (`ON CONFLICT DO UPDATE`) rendent le chargement idempotent — on peut relancer le pipeline sans créer de doublons

**Tables créées :**

| Table | Contenu | Clé primaire |
|-------|---------|--------------|
| `arrondissement` | 20 arrondissements + polygones GPS (PostGIS) | `code` |
| `prix_median` | Prix/m² médian et moyen par arrondissement et année | `(arrondissement_code, annee)` |
| `indicateur` | Les 4 scores composites en format long | `(arrondissement_code, nom, annee)` |
| `logement_social` | Nombre et part de logements sociaux | `(arrondissement_code, annee)` |
| `transaction_dvf` | Échantillon de 50 000 transactions avec coordonnées GPS | `id` auto-incrémenté |

**Accès dashboard PostgreSQL :** http://localhost:8080 (Adminer)
- Système : PostgreSQL — Serveur : `postgres` — User : `urban` — Pwd : `urban_dev_pwd` — Base : `urban_data`

---

### 5.2 MongoDB — La couche brute et catalogue

MongoDB stocke la **couche Bronze** et les métadonnées.

**Pourquoi MongoDB ?**
- Chaque source Bronze a un **schéma différent** : un CSV DVF n'a pas la même structure qu'un GeoJSON OSM ni qu'un JSON AIRPARIF → le NoSQL est naturellement adapté à cette hétérogénéité
- Le **data catalog** est construit via une agrégation MongoDB native directement sur `bronze_raw` (opérateurs `$group`, `$sum`, `$max`) sans écrire de code Python supplémentaire
- Les événements de streaming ont une durée de vie limitée → le **TTL index** natif MongoDB purge automatiquement les documents après 30 jours

**Collections créées :**

| Collection | Contenu | Particularité |
|------------|---------|---------------|
| `bronze_raw` | Un document par fichier Bronze : payload brut + checksum SHA256 + métadonnées d'ingestion | Index unique sur le chemin du fichier |
| `data_catalog` | Une entrée agrégée par source : taille, fraîcheur, fournisseur, qualité | Construit par pipeline d'agrégation MongoDB depuis `bronze_raw` |
| `stream_events` | Événements du micro-batch consolidé | TTL index : purge automatique après 30 jours |

**Structure d'un document `bronze_raw` :**
```json
{
  "source": "qualite_air",
  "path": "qualite_air_paris.json",
  "format": "json",
  "size_bytes": 2048,
  "checksum": "sha256:a3f9...",
  "ingested_at": "2025-05-22T10:00:00Z",
  "payload_kind": "json",
  "sample": [ { "arrondissement": 1, "iqa_moyen": 68 } ]
}
```

**Accès dashboard MongoDB :** http://localhost:8081 (Mongo Express)
- User : `urban-admin` — Pwd : `urban_dev_pwd`

---

## 6. Schéma récapitulatif du pipeline complet

```
APIs publiques (14 sources)
         │
         ▼
┌─────────────────────────────────────────────┐
│  COUCHE BRONZE  data/bronze/                │
│  Fichiers bruts : JSON, CSV, GeoJSON        │
│  Dont : commissariats_paris.json            │
│         pompiers_paris.json (BSPP)          │
│  → Sauvegardé aussi dans MongoDB            │
│    (bronze_raw + data_catalog)              │
└─────────────────────────────────────────────┘
         │  Nettoyage, filtres, calculs
         ▼
┌─────────────────────────────────────────────┐
│  COUCHE SILVER  data/silver/                │
│  Fichiers Parquet normalisés par thème      │
│  prix_m2 calculé, arrondissements extraits  │
│  scores air/bruit/circulation standardisés  │
│  securite_urbaine.parquet (commissariats    │
│  + casernes, enrichi par geo-join GPS)      │
└─────────────────────────────────────────────┘
         │  Agrégations + indicateurs composites
         ▼
┌─────────────────────────────────────────────┐
│  COUCHE GOLD  data/gold/                    │
│  agregats_arrondissements.parquet           │
│  indicateurs_custom.parquet                 │
│  I3 sécurité = criminalité 60%             │
│              + commissariats 25%            │
│              + pompiers 15%                 │
│  → Chargé dans PostgreSQL                   │
│    (prix_median, indicateur, transaction)   │
└─────────────────────────────────────────────┘
         │
         ▼
┌────────────────┐    ┌────────────────────┐
│  PostgreSQL    │    │  API FastAPI        │
│  (Gold)        │───▶│  localhost:8000     │
│  localhost:8080│    └─────────┬──────────┘
└────────────────┘              │
┌────────────────┐              ▼
│  MongoDB       │    ┌────────────────────┐
│  (Bronze+Meta) │    │  Dashboard nginx    │
│  localhost:8081│    │  localhost:3000     │
└────────────────┘    └────────────────────┘
```

---

## 7. Synthèse

Le projet Urban Data Explorer met en œuvre une architecture de données complète :

- **14 sources hétérogènes** collectées via des APIs publiques avec un mécanisme de fallback robuste
- **3 couches de transformation** progressives du brut vers l'agrégé
- **4 indicateurs composites** construits par combinaison pondérée de sous-scores normalisés sur 0–10, dont I3 Sécurité enrichi de 3 composantes (criminalité, commissariats, pompiers)
- **2 bases de données complémentaires** : MongoDB pour la flexibilité du schéma et la traçabilité des sources, PostgreSQL pour les requêtes analytiques filtrables et les données géospatiales
- **1 API FastAPI** et **1 dashboard** pour exposer les résultats aux utilisateurs finaux
