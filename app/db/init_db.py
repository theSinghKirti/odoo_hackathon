import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.password_service import hash_password

logger = logging.getLogger(__name__)


async def init_db(session: AsyncSession) -> None:
    """
    Initializes database with the reference tenant (Brightloop Software)
    and the primary Admin user if not already present.
    """
    # 1. Seed Reference Tenant Organization
    stmt = select(Organization).where(Organization.slug == settings.INITIAL_TENANT_SLUG)
    res = await session.execute(stmt)
    org = res.scalars().first()

    if not org:
        logger.info(f"Seeding reference tenant: {settings.INITIAL_TENANT_NAME}")
        org = Organization(
            name=settings.INITIAL_TENANT_NAME,
            slug=settings.INITIAL_TENANT_SLUG,
            is_active=True,
        )
        session.add(org)
        await session.flush()
    else:
        logger.info(f"Reference tenant '{org.name}' already exists.")

    # 2. Seed Primary Admin User
    stmt_user = select(User).where(
        User.organization_id == org.id,
        User.email == settings.FIRST_ADMIN_EMAIL.lower().strip(),
    )
    res_user = await session.execute(stmt_user)
    admin_user = res_user.scalars().first()

    if not admin_user:
        logger.info(f"Seeding primary admin user: {settings.FIRST_ADMIN_EMAIL}")
        admin_user = User(
            organization_id=org.id,
            full_name=settings.FIRST_ADMIN_NAME,
            email=settings.FIRST_ADMIN_EMAIL.lower().strip(),
            password_hash=hash_password(settings.FIRST_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        session.add(admin_user)
        await session.commit()
        logger.info("Database initialization completed successfully.")
    else:
        logger.info("Primary admin user already exists.")
        await session.commit()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with async_session_factory() as session:
        await init_db(session)


if __name__ == "__main__":
    asyncio.run(main())

