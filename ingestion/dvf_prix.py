"""
ingestion/dvf_prix.py
Télécharge les fichiers DVF pour Paris (dept 75).
IMPORTANT : le répertoire geo-dvf/latest ne contient que 2021-2025.
2019 et 2020 ne sont plus disponibles.
"""
import sys
from pathlib import Path
import requests
from loguru import logger
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import BRONZE_DIR, DVF_BASE_URL, DVF_YEARS

DVF_DIR = BRONZE_DIR / "dvf"
DVF_DIR.mkdir(exist_ok=True)


def download_file(url: str, dest: Path) -> bool:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (urban-data-explorer/1.0)"}
        r = requests.get(url, stream=True, timeout=180, headers=headers)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True,
            desc=dest.name, leave=False
        ) as bar:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))
        if dest.stat().st_size < 10000:
            dest.unlink()
            return False
        return True
    except Exception as e:
        logger.error(f"  Erreur : {e}")
        if dest.exists():
            dest.unlink()
        return False


def run():
    logger.info(f"Ingestion DVF — années {DVF_YEARS}")
    logger.info("  (geo-dvf/latest contient uniquement 2021-2025)")
    success = 0
    for year in DVF_YEARS:
        dest = DVF_DIR / f"dvf_75_{year}.csv.gz"
        if dest.exists():
            logger.info(f"  {dest.name} déjà présent, skip")
            success += 1
            continue
        url = DVF_BASE_URL.format(year=year)
        logger.info(f"  Téléchargement {url}…")
        if download_file(url, dest):
            logger.success(f"  ✓ {dest.name} ({dest.stat().st_size / 1e6:.1f} Mo)")
            success += 1
        else:
            logger.warning(f"  ✗ Échec pour {year}")
    logger.info(f"DVF : {success}/{len(DVF_YEARS)} fichiers téléchargés")
    return success > 0


if __name__ == "__main__":
    run()
