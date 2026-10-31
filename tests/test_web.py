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
    client.cookies.set(settings.COOKIE_NAME, token)

    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Tenant Alpha Workspace" in response.text
    assert "tenant-alpha" in response.text
    assert "Admin Alpha" in response.text


@pytest.mark.asyncio
async def test_admin_products_page_renders(client: AsyncClient, seed_data):
    """Milestone F2: GET /admin/products renders Product Catalog with variant controls."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    client.cookies.set(settings.COOKIE_NAME, token)

    response = await client.get("/admin/products")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Product Catalog" in response.text


@pytest.mark.asyncio
async def test_admin_plans_page_renders(client: AsyncClient, seed_data):
    """Milestone F3: GET /admin/plans renders Subscription Plans cards grid."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    client.cookies.set(settings.COOKIE_NAME, token)

    response = await client.get("/admin/plans")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Subscription Plans" in response.text


@pytest.mark.asyncio
async def test_admin_taxes_and_discounts_pages_render(client: AsyncClient, seed_data):
    """Milestone F4: GET /admin/taxes and /admin/discounts render configuration tables."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    client.cookies.set(settings.COOKIE_NAME, token)

    taxes_resp = await client.get("/admin/taxes")
    assert taxes_resp.status_code == 200
    assert "Tax Rules" in taxes_resp.text

    discounts_resp = await client.get("/admin/discounts")
    assert discounts_resp.status_code == 200
    assert "Discount Rules" in discounts_resp.text


@pytest.mark.asyncio
async def test_staff_quotations_and_templates_render(client: AsyncClient, seed_data):
    """Milestone F5: GET /staff/quotations and template manager render correctly."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    client.cookies.set(settings.COOKIE_NAME, token)

    templates_resp = await client.get("/admin/quotation-templates")
    assert templates_resp.status_code == 200
    assert "Quotation Templates" in templates_resp.text

    quotations_resp = await client.get("/staff/quotations")
    assert quotations_resp.status_code == 200
    assert "Quotations" in quotations_resp.text

    form_resp = await client.get("/staff/quotations/new")
    assert form_resp.status_code == 200


@pytest.mark.asyncio
async def test_staff_subscriptions_page_renders(client: AsyncClient, seed_data):
    """Milestone F6: GET /staff/subscriptions renders subscription lifecycle dashboard."""
    admin = seed_data["admin_a"]
    token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
    )
    client.cookies.set(settings.COOKIE_NAME, token)

    subs_resp = await client.get("/staff/subscriptions")
    assert subs_resp.status_code == 200
    assert "Subscriptions" in subs_resp.text


@pytest.mark.asyncio
async def test_register_page_has_confirm_password(client: AsyncClient):
    """GET /register renders registration form with confirm_password."""
    response = await client.get("/register")
    assert response.status_code == 200
    assert "confirm_password" in response.text
    assert "Confirm Password" in response.text


@pytest.mark.asyncio
async def test_reset_password_page_renders(client: AsyncClient):
    """GET /reset-password renders standalone password reset page with confirmation."""
    response = await client.get("/reset-password?token=sample_token_xyz")
    assert response.status_code == 200
    assert "Reset Password" in response.text
    assert "new_password" in response.text
    assert "confirm_password" in response.text
    assert "sample_token_xyz" in response.text


@pytest.mark.asyncio
async def test_access_denied_page_renders(client: AsyncClient):
    """GET /access-denied renders 403 unauthorized access page."""
    response = await client.get("/access-denied")
    assert response.status_code == 403
    assert "Access Denied" in response.text
    assert "403" in response.text
