from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import async_session_factory
from app.web.routes import router as web_router

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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

# Exception handlers for web user experience
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    # If API call, preserve standard JSON response
    if request.url.path.startswith("/api/"):
        headers = getattr(exc, "headers", None)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    # If 403 Forbidden on a browser request, render access_denied.html
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        return templates.TemplateResponse(
            request=request,
            name="auth/access_denied.html",
            context={
                "user": None,
                "detail": str(exc.detail),
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # If 401 Unauthorized on browser route, redirect to login
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    headers = getattr(exc, "headers", None)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)


# Mount Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount API Routers
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(health.router)  # Direct /health endpoint

# Mount Server-Rendered Web Routes
app.include_router(web_router)
