"""Download the ByMykel/CSGO-API skin catalog (once) and load it into the local DB.

Run from the project root: .venv\\Scripts\\python.exe scripts\\load_catalog.py [--refresh]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.catalog.store import CatalogStore, download_catalog, parse_catalog
from app.db.session import init_db, make_engine

CATALOG_FILE = Path("data/catalog/skins.json")


def main() -> None:
    if "--refresh" in sys.argv or not CATALOG_FILE.exists():
        print(f"Downloading catalog to {CATALOG_FILE} ...")
        download_catalog(CATALOG_FILE)
    store = CatalogStore(init_db(make_engine()))
    total = store.load(parse_catalog(CATALOG_FILE))
    print(f"Catalog loaded: {total} skins")
    for side in ("ct", "t"):
        slots = store.slots(side)
        print(f"  {side}: {len(slots)} weapons, {sum(s.skins for s in slots)} skins")


if __name__ == "__main__":
    main()
