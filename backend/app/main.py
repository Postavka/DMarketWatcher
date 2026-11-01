"""FastAPI app. Run locally: .venv\\Scripts\\python.exe -m uvicorn app.main:create_app --factory --app-dir backend"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import Settings
from app.state import AppState, build_state, ensure_catalog


def create_app(state: AppState | None = None) -> FastAPI:
    """`state` is injected by tests; in normal runs it is built from `.env` on startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.app_state = state or build_state(Settings())
        if state is None:  # injected state (tests) is used as given; never reads local data files
            await ensure_catalog(app.state.app_state)
        try:
            yield
        finally:
            await app.state.app_state.aclose()

    app = FastAPI(title="DMarket Watcher", lifespan=lifespan)
    # Local dev frontend (Vite) only; the API is read-only and bound to localhost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app
