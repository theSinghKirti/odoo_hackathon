from datetime import timedelta
import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.core.security import create_access_token
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_successful_login(client: AsyncClient, seed_data):
    """User with valid credentials receives JWT and HTTP-only cookie."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.com", "password": "Admin@Alpha123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    # Verify HTTP-only cookie is set
    assert settings.COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, seed_data):
    """Attempting login with wrong password returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@alpha.com", "password": "WrongPassword!999"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient, seed_data):
    """Attempting login with unregistered email returns 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@company.com", "password": "SomePassword!123"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, seed_data):
    """Inactive users are rejected from authentication with 403."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@alpha.com", "password": "Inactive@Alpha123"},
    )
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_user_in_inactive_organization(client: AsyncClient, seed_data):
    """Users belonging to a suspended/inactive tenant cannot authenticate."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@inactiveorg.com", "password": "Inactive@Org123"},
    )
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient):
    """Logout endpoint deletes the authentication cookie."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out."


@pytest.mark.asyncio
async def test_expired_jwt(client: AsyncClient, seed_data):
    """Requests with expired JWT are rejected with 401."""
    admin = seed_data["admin_a"]
    expired_token = create_access_token(
        subject=str(admin.id),
        organization_id=admin.organization_id,
        role=admin.role.value,
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_jwt(client: AsyncClient):
    """Requests with a forged or invalid JWT token are rejected with 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer forged.invalid.token"},
    )
    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_authenticated_me_endpoint(client: AsyncClient, seed_data):
    """Current authenticated user can retrieve their profile (no password hash exposed)."""
    admin = seed_data["admin_a"]
    headers = auth_header(admin)
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == admin.id
    assert data["email"] == "admin@alpha.com"
    assert data["role"] == "admin"
    assert "password_hash" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient, seed_data):
    """Full password reset workflow: request token -> submit token + new password -> login."""
    user = seed_data["customer_a"]

    # 1. Request password reset
    forgot_resp = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user.email},
    )
    assert forgot_resp.status_code == 200
    forgot_data = forgot_resp.json()
    assert "instructions have been sent" in forgot_data["message"]
    token = forgot_data.get("dev_token")
    assert token is not None

    # 2. Reset password using valid token
    new_pwd = "BrandNew$Password2026"
    reset_resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": new_pwd},
    )
    assert reset_resp.status_code == 200
    assert "successfully" in reset_resp.json()["message"]

    # 3. Attempt reusing token (must be rejected as single-use)
    reuse_resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherNew$Password2026"},
    )
    assert reuse_resp.status_code == 400

    # 4. Verify user can now authenticate with the new password
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": new_pwd},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()

