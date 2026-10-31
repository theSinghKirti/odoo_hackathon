import pytest
from httpx import AsyncClient
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient):
    """Requests to protected endpoints without authentication return 401."""
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_access_to_admin_route(client: AsyncClient, seed_data):
    """Admin can successfully access administrative endpoints."""
    admin = seed_data["admin_a"]
    headers = auth_header(admin)
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) >= 1


@pytest.mark.asyncio
async def test_staff_cannot_access_admin_route(client: AsyncClient, seed_data):
    """Staff role is denied access to admin-only endpoints with 403."""
    staff = seed_data["staff_a"]
    headers = auth_header(staff)
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


@pytest.mark.asyncio
async def test_customer_cannot_access_staff_or_admin_routes(client: AsyncClient, seed_data):
    """Customer role is denied access to both staff and admin routes."""
    customer = seed_data["customer_a"]
    headers = auth_header(customer)

    # 1. Denied admin route
    admin_resp = await client.get("/api/v1/admin/users", headers=headers)
    assert admin_resp.status_code == 403

    # 2. Denied staff route (customers list)
    staff_resp = await client.get("/api/v1/customers", headers=headers)
    assert staff_resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_staff_account(client: AsyncClient, seed_data):
    """Admin can create a new Staff account within their tenant."""
    admin = seed_data["admin_a"]
    headers = auth_header(admin)
    payload = {
        "full_name": "New Operations Staff",
        "email": "ops.staff@alpha.com",
        "password": "StaffPassword#2026",
    }
    response = await client.post("/api/v1/admin/staff", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "staff"
    assert data["email"] == "ops.staff@alpha.com"
    assert data["organization_id"] == admin.organization_id


@pytest.mark.asyncio
async def test_staff_and_customer_cannot_create_staff(client: AsyncClient, seed_data):
    """Non-admin users cannot provision Staff accounts."""
    payload = {
        "full_name": "Unauthorized Staff",
        "email": "unauth@alpha.com",
        "password": "Password#123",
    }

    # Staff attempt
    staff_headers = auth_header(seed_data["staff_a"])
    resp_staff = await client.post("/api/v1/admin/staff", json=payload, headers=staff_headers)
    assert resp_staff.status_code == 403

    # Customer attempt
    cust_headers = auth_header(seed_data["customer_a"])
    resp_cust = await client.post("/api/v1/admin/staff", json=payload, headers=cust_headers)
    assert resp_cust.status_code == 403


@pytest.mark.asyncio
async def test_public_registration_defaults_to_customer_role(client: AsyncClient, seed_data):
    """Public registration always assigns Customer role, never Admin or Staff."""
    payload = {
        "full_name": "Public Registrant",
        "email": "public.registrant@alpha.com",
        "password": "StrongPassword!2026",
        "organization_slug": "tenant-alpha",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "customer"

