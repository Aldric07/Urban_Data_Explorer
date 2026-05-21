# Data Catalog — Urban Data Explorer

## Principes de sourcing

Toutes les données utilisées sont **open data** accessibles sans clé API payante.
Chaque source est justifiée par rapport à la problématique du projet.

---

## 1. Données immobilières (indicateurs de base)

### DVF — Demandes de Valeurs Foncières
| Champ | Valeur |
|---|---|
| **Source** | Ministère de l'économie via data.gouv.fr |
| **URL** | `https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/75.csv.gz` |
| **Format** | CSV.gz (~50-80 Mo par année) |
| **Licence** | Licence Ouverte Etalab 2.0 |
| **Fréquence** | Annuelle (données N-1) |
| **Justification** | Source de référence officielle pour les prix de vente immobiliers. Contient chaque transaction avec prix, surface, type de bien, géolocalisation. Permet le calcul du prix/m² médian par arrondissement et son évolution. |
| **Contraintes** | Pas de données de location. Délai de publication ~12 mois. |
| **Colonnes utilisées** | `date_mutation`, `valeur_fonciere`, `code_postal`, `type_local`, `surface_reelle_bati`, `longitude`, `latitude` |

### RPLS — Répertoire des Logements Locatifs Sociaux
| Champ | Valeur |
|---|---|
| **Source** | Ministère du logement via data.gouv.fr |
| **URL** | `https://www.data.gouv.fr/fr/datasets/5b51a3e0c751df48e3a6de74/` |
| **Format** | CSV |
| **Licence** | Licence Ouverte Etalab 2.0 |
| **Justification** | Permet de calculer la part des logements sociaux par arrondissement, indicateur clé de la mixité sociale et de l'accessibilité au logement. |

### Encadrement des loyers DRIHL
| Champ | Valeur |
|---|---|
| **Source** | DRIHL Île-de-France via data.gouv.fr |
| **URL** | `https://www.data.gouv.fr/fr/datasets/5fee4180-de28-4f42-9389-b33d58b8eca0/` |
| **Format** | CSV |
| **Justification** | Loyers de référence légaux par zone, nb pièces et époque de construction. Complète DVF (location vs achat). Permet l'indicateur tension immobilière. |

---

## 2. Données socio-économiques

### INSEE Filosofi — Revenus médians
| Champ | Valeur |
|---|---|
| **Source** | INSEE |
| **URL** | `https://www.insee.fr/fr/statistiques/7233950` |
| **Format** | CSV (dans ZIP) |
| **Licence** | Licence Ouverte |
| **Justification** | Revenus médians par commune/IRIS permettant de calculer l'accessibilité financière au logement (ratio prix/revenu). Indicateur de mixité sociale. |
| **Colonnes utilisées** | `Q2` (médiane), `D1`, `D9` (déciles), taux de pauvreté |

---

## 3. Données d'accessibilité

### IDFM — Arrêts de transport
| Champ | Valeur |
|---|---|
| **Source** | Île-de-France Mobilités |
| **URL** | `https://data.iledefrance-mobilites.fr/` |
| **Format** | JSON via API REST |
| **Licence** | Licence ODbL |
| **Justification** | Densité des arrêts de métro, RER, bus par arrondissement. Composante majeure du score d'accessibilité. |

### Ministère de l'Éducation — Annuaire
| Champ | Valeur |
|---|---|
| **Source** | data.education.gouv.fr |
| **URL** | `https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/` |
| **Format** | JSON via API REST |
| **Licence** | Licence Ouverte |
| **Justification** | Nombre d'établissements scolaires par arrondissement (écoles, collèges, lycées). Critère de qualité résidentielle pour familles. |

---

## 4. Données environnementales et qualité de vie

### OpenStreetMap (Overpass API) — Espaces verts
| Champ | Valeur |
|---|---|
| **Source** | OpenStreetMap contributors |
| **URL** | `https://overpass-api.de/api/interpreter` |
| **Format** | JSON |
| **Licence** | ODbL |
| **Justification** | Parcs, jardins, espaces naturels. Composante du score qualité de vie. Données maintenues par la communauté, très à jour. |

### AIRPARIF — Qualité de l'air
| Champ | Valeur |
|---|---|
| **Source** | AIRPARIF (avec données statiques de repli si API indisponible) |
| **Justification** | Indices de qualité de l'air (IQA, NO2, PM2.5) par arrondissement. Composante santé du score qualité de vie. Données documentées comme statiques 2023 si API indisponible. |

---

## 5. Données de sécurité

### Faits constatés — Police nationale
| Champ | Valeur |
|---|---|
| **Source** | Ministère de l'Intérieur via data.gouv.fr |
| **URL** | `https://www.data.gouv.fr/fr/datasets/5d34dc76-d3d2-4d97-8fd4-694f5d81a490/` |
| **Format** | CSV |
| **Licence** | Licence Ouverte |
| **Justification** | Faits constatés par zone géographique. Composante de l'indice de sécurité. |
| **Limite** | Granularité départementale ou communale selon les années ; interpolation nécessaire si données seulement à l'échelle 75. |

---

## 6. Données géographiques

### Contours arrondissements
| Champ | Valeur |
|---|---|
| **Source** | Paris Open Data / geo.api.gouv.fr |
| **Format** | GeoJSON |
| **Justification** | Fondation de toutes les visualisations cartographiques. Sert à la jointure spatiale coordonnées → arrondissement. |

---

## Indicateurs custom — Justification méthodologique

### Score d'accessibilité urbaine (fusion transport + éducation + centralité)
Répond à la question : *"Comment est desservi cet arrondissement ?"*
Pondération justifiée par l'importance relative des critères (transport > éducation > distance).

### Score de qualité de vie (espaces verts + qualité air)
Répond à : *"Est-il agréable d'y vivre au quotidien ?"*
Deux dimensions santé complémentaires : verts (bien-être) et air (santé physique).

### Indice de sécurité (faits constatés normalisés)
Répond à : *"Quel est le niveau de sécurité perçu ?"*
Normalisé entre 0-10 pour comparabilité. Données officielles police.

### Tension immobilière (prix/revenu)
Répond à : *"Peut-on se loger ici avec un revenu local médian ?"*
Croise DVF (Silver) et Filosofi (Silver). Mesure d'accessibilité socio-économique — indicateur le plus original du projet.
