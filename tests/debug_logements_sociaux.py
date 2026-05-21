"""
tests/debug_logements_sociaux.py
Diagnostic complet de la chaîne logements sociaux : Bronze → Silver → Gold → API
Usage : python3 tests/debug_logements_sociaux.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, SILVER_DIR, GOLD_DIR

SEP = "─" * 60

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg):   print(f"  ✅  {msg}")
def err(msg):  print(f"  ❌  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def info(msg): print(f"  ℹ️   {msg}")


# ══════════════════════════════════════════════════════════════════
# 1. BRONZE — fichier CSV
# ══════════════════════════════════════════════════════════════════
section("1. BRONZE — logements_sociaux_paris.csv")

bronze_path = BRONZE_DIR / "logements_sociaux_paris.csv"

if not bronze_path.exists():
    err(f"Fichier absent : {bronze_path}")
    print("\n  → Fix : python3 ingestion/logements_sociaux.py")
    sys.exit(1)

ok(f"Fichier présent ({bronze_path.stat().st_size} octets)")

# Lire le contenu brut
raw = bronze_path.read_text(encoding="utf-8", errors="replace")
lines = raw.strip().splitlines()
info(f"Nombre de lignes : {len(lines)}")
info(f"Ligne 1 (header) : {lines[0]!r}")
if len(lines) > 1:
    info(f"Ligne 2 (données) : {lines[1]!r}")
if len(lines) > 2:
    info(f"Ligne 3 (données) : {lines[2]!r}")

# Détecte le séparateur
sep_detected = ";" if lines[0].count(";") > lines[0].count(",") else ","
info(f"Séparateur détecté : {sep_detected!r}")

# Parse avec pandas
import pandas as pd
try:
    df_bronze = pd.read_csv(bronze_path, sep=sep_detected, encoding="utf-8")
    ok(f"Lecture pandas réussie : {len(df_bronze)} lignes, {len(df_bronze.columns)} colonnes")
    info(f"Colonnes : {list(df_bronze.columns)}")
    info(f"Types   : {dict(df_bronze.dtypes)}")
    print(f"\n{df_bronze.to_string(index=False)}")
except Exception as e:
    err(f"Erreur lecture pandas : {e}")
    sys.exit(1)

# Vérifie les colonnes attendues
expected_cols = {"arrondissement", "part_ls_pct", "nb_logements_sociaux"}
missing = expected_cols - set(df_bronze.columns)
if missing:
    err(f"Colonnes manquantes : {missing}")
else:
    ok(f"Toutes les colonnes attendues présentes")

# Vérifie les valeurs
if "part_ls_pct" in df_bronze.columns:
    null_pct = df_bronze["part_ls_pct"].isna().sum()
    if null_pct > 0:
        err(f"part_ls_pct : {null_pct} valeurs nulles")
    else:
        ok(f"part_ls_pct : min={df_bronze['part_ls_pct'].min()}, max={df_bronze['part_ls_pct'].max()}")

if "nb_logements_sociaux" in df_bronze.columns:
    ok(f"nb_logements_sociaux : min={df_bronze['nb_logements_sociaux'].min()}, max={df_bronze['nb_logements_sociaux'].max()}")

if "arrondissement" in df_bronze.columns:
    arrs = sorted(df_bronze["arrondissement"].unique())
    info(f"Arrondissements : {arrs}")
    if len(arrs) == 20:
        ok("20 arrondissements couverts")
    else:
        err(f"Seulement {len(arrs)} arrondissements")


# ══════════════════════════════════════════════════════════════════
# 2. SILVER — logements_sociaux.parquet
# ══════════════════════════════════════════════════════════════════
section("2. SILVER — logements_sociaux.parquet")

silver_path = SILVER_DIR / "logements_sociaux.parquet"

if not silver_path.exists():
    err(f"Fichier absent : {silver_path}")
    print("  → Fix : python3 pipeline/silver_logements_sociaux.py")
else:
    ok(f"Fichier présent ({silver_path.stat().st_size} octets)")
    try:
        df_silver = pd.read_parquet(silver_path)
        ok(f"Lecture parquet : {len(df_silver)} lignes, {len(df_silver.columns)} colonnes")
        info(f"Colonnes : {list(df_silver.columns)}")
        print(f"\n{df_silver.to_string(index=False)}")

        for col in ["part_logements_sociaux_pct", "nb_logements_sociaux"]:
            if col in df_silver.columns:
                nulls = df_silver[col].isna().sum()
                status = ok if nulls == 0 else err
                status(f"{col} : {nulls} nulls, valeurs={df_silver[col].tolist()}")
            else:
                err(f"Colonne manquante : {col}")
    except Exception as e:
        err(f"Erreur lecture parquet : {e}")


# ══════════════════════════════════════════════════════════════════
# 3. GOLD — gold_final.parquet
# ══════════════════════════════════════════════════════════════════
section("3. GOLD — gold_final.parquet")

gold_path = GOLD_DIR / "gold_final.parquet"

if not gold_path.exists():
    err(f"Fichier absent : {gold_path}")
    print("  → Fix : python3 pipeline/run_pipeline.py")
else:
    ok(f"Fichier présent ({gold_path.stat().st_size} octets)")
    try:
        df_gold = pd.read_parquet(gold_path)
        ok(f"Lecture parquet : {len(df_gold)} lignes, {len(df_gold.columns)} colonnes")
        info(f"Toutes les colonnes : {list(df_gold.columns)}")

        # Cherche toutes les colonnes logements sociaux
        ls_cols = [c for c in df_gold.columns if "logement" in c.lower() or "ls" in c.lower()]
        info(f"Colonnes logements sociaux trouvées : {ls_cols}")

        if not ls_cols:
            err("Aucune colonne logements sociaux dans le Gold !")
        else:
            for col in ls_cols:
                nulls = df_gold[col].isna().sum()
                ok(f"{col} : {nulls}/{len(df_gold)} nulls")
                # Aperçu dernière année
                derniere = df_gold["annee"].max()
                apercu = df_gold[df_gold["annee"] == derniere][["arrondissement", col]].head(5)
                print(f"    Aperçu {derniere} :\n{apercu.to_string(index=False)}")
    except Exception as e:
        err(f"Erreur lecture parquet : {e}")


# ══════════════════════════════════════════════════════════════════
# 4. API — endpoint /logements-sociaux
# ══════════════════════════════════════════════════════════════════
section("4. API — test endpoint /logements-sociaux")

import requests

API_BASE = "http://localhost:8000"
HEADERS  = {"X-API-Key": "urban-explorer-dev-key"}

try:
    r = requests.get(f"{API_BASE}/health", timeout=3)
    if r.status_code == 200:
        ok(f"API active : {r.json()}")
    else:
        warn(f"API répond {r.status_code}")

    r = requests.get(f"{API_BASE}/logements-sociaux", headers=HEADERS, timeout=5)
    if r.status_code == 200:
        data = r.json()
        ok(f"/logements-sociaux : {len(data)} enregistrements")
        if data:
            info(f"Clés disponibles : {list(data[0].keys())}")
            info(f"Premier enregistrement : {data[0]}")
            # Vérifie les valeurs
            pcts = [d.get("part_logements_sociaux_pct") for d in data if d.get("part_logements_sociaux_pct") is not None]
            if pcts:
                ok(f"part_logements_sociaux_pct : {len(pcts)} valeurs non-null, exemple={pcts[:3]}")
            else:
                err("part_logements_sociaux_pct est toujours null dans la réponse API !")
        else:
            err("L'endpoint retourne une liste vide !")
    else:
        err(f"/logements-sociaux : {r.status_code} — {r.text[:200]}")

except requests.exceptions.ConnectionError:
    warn("API non démarrée — skip test endpoint")
    info("Lance l'API avec : python3 -m uvicorn api.main:app --reload --port 8000")


# ══════════════════════════════════════════════════════════════════
# 5. DASHBOARD — indicateur logements sociaux dans gold_final
# ══════════════════════════════════════════════════════════════════
section("5. DIAGNOSTIC — indicateur part_logements_sociaux_pct dans Gold")

if gold_path.exists():
    df = pd.read_parquet(gold_path)
    col = next((c for c in df.columns if "part_log" in c or "part_ls" in c), None)
    if col:
        derniere = df["annee"].max()
        df_last = df[df["annee"] == derniere][["arrondissement", col]].sort_values("arrondissement")
        ok(f"Colonne utilisée pour la carte : '{col}'")
        print(f"\n  Valeurs par arrondissement ({derniere}) :")
        print(df_last.to_string(index=False))

        nulls = df_last[col].isna().sum()
        if nulls == 0:
            ok(f"Aucun null — données complètes pour la carte ✓")
        else:
            err(f"{nulls} arrondissements sans données logements sociaux")
    else:
        err("Colonne part_logements_sociaux_pct ABSENTE du Gold final !")
        err("La carte affichera toujours noir pour cet indicateur.")
        print("\n  → Fix complet :")
        print("    1. rm data/bronze/logements_sociaux_paris.csv")
        print("    2. python3 ingestion/logements_sociaux.py")
        print("    3. rm -rf data/silver/logements_sociaux.parquet data/gold/")
        print("    4. python3 pipeline/run_pipeline.py")

print(f"\n{SEP}")
print("  DIAGNOSTIC TERMINÉ")
print(SEP)
