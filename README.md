# DMarketWatcher
PetProject for skins collecting

Read-only helper for CS2 skins on DMarket: it never buys, lists or trades. Current mode: **colour build** —
pick a side, a colour and a budget, get one cheapest offer per matching skin (optionally narrowed by Claude).

## Setup
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd frontend && npm install
```
Create `.env` in the project root (it is git-ignored):
```
DMARKET_PUBLIC_KEY=...
DMARKET_SECRET_KEY=...
ANTHROPIC_API_KEY=...   # optional: enables the AI shortlist
```

## Run (two terminals)
```
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --app-dir backend   # API on :8000
cd frontend && npm run dev                                                           # UI on :5173
```
The first start downloads the skin catalog (`data/catalog/skins.json`); the first search of a colour can take a
couple of minutes (images and prices are cached afterwards).

## Tests
```
.venv\Scripts\python.exe -m pytest
cd frontend && npm test
```
