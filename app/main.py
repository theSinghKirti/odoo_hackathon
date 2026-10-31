from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import async_session_factory
from app.web.routes import router as web_router

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed reference tenant and admin if needed
    try:
        async with async_session_factory() as session:
            await init_db(session)
    except Exception as e:
        # Don't crash on startup if DB is not yet migrated or reachable
        pass
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API Routers
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(health.router)  # Direct /health endpoint

# Mount Server-Rendered Web Routes
app.include_router(web_router)

