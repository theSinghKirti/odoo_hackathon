import asyncio
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test configuration
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "False"
os.environ["SECRET_KEY"] = "test_secret_key_32_characters_long_min!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_app.db"
os.environ["ENABLE_DEV_PASSWORD_RESET_SIMULATION"] = "True"

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_async_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.customer import Customer
from app.services.password_service import hash_password

# Create isolated test engine
test_engine = create_async_engine(
    "sqlite+aiosqlite:///./test_app.db",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Drop and recreate all tables for complete isolation between tests."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated database session."""
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Provides an HTTPX AsyncClient with overridden DB dependency."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_data(db_session: AsyncSession):
    """
    Seeds two separate organizations with Admin, Staff, and Customer users
    to test multi-tenancy and RBAC thoroughly.
    """
    # 1. Organization A (Tenant Alpha)
    org_a = Organization(name="Tenant Alpha", slug="tenant-alpha", is_active=True)
    db_session.add(org_a)
    await db_session.flush()

    admin_a = User(
        organization_id=org_a.id,
        full_name="Admin Alpha",
        email="admin@alpha.com",
        password_hash=hash_password("Admin@Alpha123"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    staff_a = User(
        organization_id=org_a.id,
        full_name="Staff Alpha",
        email="staff@alpha.com",
        password_hash=hash_password("Staff@Alpha123"),
        role=UserRole.STAFF,
        is_active=True,
        is_verified=True,
    )
    customer_a = User(
        organization_id=org_a.id,
        full_name="Customer Alpha",
        email="customer@alpha.com",
        password_hash=hash_password("Customer@Alpha123"),
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    inactive_user_a = User(
        organization_id=org_a.id,
        full_name="Inactive User",
        email="inactive@alpha.com",
        password_hash=hash_password("Inactive@Alpha123"),
        role=UserRole.CUSTOMER,
        is_active=False,
        is_verified=True,
    )
    cust_record_a = Customer(
        organization_id=org_a.id,
        name="Alpha Customer Co",
        email="client@alphaco.com",
        is_active=True,
    )
    db_session.add_all([admin_a, staff_a, customer_a, inactive_user_a, cust_record_a])

    # 2. Organization B (Tenant Beta)
    org_b = Organization(name="Tenant Beta", slug="tenant-beta", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    admin_b = User(
        organization_id=org_b.id,
        full_name="Admin Beta",
        email="admin@beta.com",
        password_hash=hash_password("Admin@Beta123"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    customer_b = User(
        organization_id=org_b.id,
        full_name="Customer Beta",
        email="customer@beta.com",
        password_hash=hash_password("Customer@Beta123"),
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=True,
    )
    cust_record_b = Customer(
        organization_id=org_b.id,
        name="Beta Customer Co",
        email="client@betaco.com",
        is_active=True,
    )
    db_session.add_all([admin_b, customer_b, cust_record_b])

    # 3. Inactive Organization (Tenant Inactive)
    org_inactive = Organization(name="Tenant Inactive", slug="tenant-inactive", is_active=False)
    db_session.add(org_inactive)
    await db_session.flush()

    user_in_inactive_org = User(
        organization_id=org_inactive.id,
        full_name="User Inactive Org",
        email="user@inactiveorg.com",
        password_hash=hash_password("Inactive@Org123"),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user_in_inactive_org)

    await db_session.commit()

    return {
        "org_a": org_a,
        "admin_a": admin_a,
        "staff_a": staff_a,
        "customer_a": customer_a,
        "inactive_user_a": inactive_user_a,
        "cust_record_a": cust_record_a,
        "org_b": org_b,
        "admin_b": admin_b,
        "customer_b": customer_b,
        "cust_record_b": cust_record_b,
        "org_inactive": org_inactive,
        "user_in_inactive_org": user_in_inactive_org,
    }


def auth_header(user: User) -> dict:
    """Helper to generate Authorization header for a user."""
    token = create_access_token(
        subject=str(user.id),
        organization_id=user.organization_id,
        role=user.role.value,
    )
    return {"Authorization": f"Bearer {token}"}
