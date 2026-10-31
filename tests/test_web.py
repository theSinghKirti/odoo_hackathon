import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient):
    """GET /health returns healthy status and DB connectivity."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"


@pytest.mark.asyncio
async def test_home_page_redirects_unauthenticated(client: AsyncClient):
    """GET / redirects unauthenticated visitor to /login."""
    response = await client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_page_renders(client: AsyncClient):
    """GET /login renders HTML login page."""
    response = await client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Welcome Back" in response.text


@pytest.mark.asyncio
async def test_register_page_renders(client: AsyncClient):
    """GET /register renders HTML registration page."""
    response = await client.get("/register")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Create Account" in response.text


@pytest.mark.asyncio
async def test_forgot_password_page_renders(client: AsyncClient):
    """GET /forgot-password renders password recovery page."""
    response = await client.get("/forgot-password")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Password Recovery" in response.text


@pytest.mark.asyncio
async def test_dashboard_redirects_when_unauthenticated(client: AsyncClient):
    """GET /dashboard redirects unauthenticated visitor to /login."""
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_dashboard_renders_when_authenticated_via_cookie(client: AsyncClient, seed_data):
    """GET /dashboard renders workspace for user authenticated with HTTP-only cookie."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    # Set cookie in client
    client.cookies.set(settings.COOKIE_NAME, token)

    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Tenant Alpha Workspace" in response.text
    assert "tenant-alpha" in response.text
    assert "Admin Alpha" in response.text

