from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_db

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """
    Service health check verifying application and database readiness.
    """
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }

