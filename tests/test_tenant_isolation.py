import pytest
from httpx import AsyncClient
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_admin_cannot_see_other_tenant_users(client: AsyncClient, seed_data):
    """
    Tenant Alpha Admin querying /api/v1/admin/users must only receive
    users belonging to Tenant Alpha, never Tenant Beta users.
    """
    admin_a = seed_data["admin_a"]
    headers_a = auth_header(admin_a)

    response = await client.get("/api/v1/admin/users", headers=headers_a)
    assert response.status_code == 200
    users = response.json()

    # All returned users must strictly belong to tenant_a
    assert len(users) > 0
    for u in users:
        assert u["organization_id"] == admin_a.organization_id
        assert "beta.com" not in u["email"]


@pytest.mark.asyncio
async def test_tenant_cannot_see_other_tenant_customers(client: AsyncClient, seed_data):
    """
    Staff from Tenant Alpha querying /api/v1/customers must only receive
    customers belonging to Tenant Alpha, never Tenant Beta customers.
    """
    staff_a = seed_data["staff_a"]
    headers_a = auth_header(staff_a)

    response = await client.get("/api/v1/customers", headers=headers_a)
    assert response.status_code == 200
    customers = response.json()

    assert len(customers) > 0
    for c in customers:
        assert c["organization_id"] == staff_a.organization_id
        assert c["email"] != "client@betaco.com"


@pytest.mark.asyncio
async def test_url_id_tampering_rejected_across_tenants(client: AsyncClient, seed_data):
    """
    IDOR / URL ID tampering test:
    A user in Tenant Alpha tries to fetch a Customer record that exists in Tenant Beta
    by directly passing Tenant Beta's customer ID in the URL.
    The system must return 404 (or reject access).
    """
    staff_a = seed_data["staff_a"]
    cust_b = seed_data["cust_record_b"]
    headers_a = auth_header(staff_a)

    # Attempt to access Tenant Beta's customer ID with Tenant Alpha's credentials
    response = await client.get(f"/api/v1/customers/{cust_b.id}", headers=headers_a)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_payload_organization_id_ignored_on_creation(client: AsyncClient, seed_data):
    """
    A user cannot spoof or alter their organization_id via request payloads.
    Customer creation must always be bound to the authenticated server-side context.
    """
    staff_a = seed_data["staff_a"]
    org_b = seed_data["org_b"]
    headers_a = auth_header(staff_a)

    payload = {
        "name": "New Alpha Client",
        "email": "newclient@alphaco.com",
        "phone": "+1234567890",
        "organization_id": org_b.id,  # Attempting to assign to Tenant B!
    }

    response = await client.post("/api/v1/customers", json=payload, headers=headers_a)
    assert response.status_code == 201
    created = response.json()

    # The created customer must be bound to staff_a's organization, NOT org_b!
    assert created["organization_id"] == staff_a.organization_id
    assert created["organization_id"] != org_b.id


@pytest.mark.asyncio
async def test_email_uniqueness_is_tenant_scoped(client: AsyncClient, seed_data):
    """
    Verify that the same email address can exist across different tenant organizations,
    enforcing true multi-tenant partitioning without cross-tenant collisions.
    """
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]

    shared_email = "shared.user@saas.com"
    pwd = "SharedUser$2026"

    # Register in Tenant A
    resp_a = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Shared User A",
            "email": shared_email,
            "password": pwd,
            "organization_slug": "tenant-alpha",
        },
    )
    assert resp_a.status_code == 201
    user_a = resp_a.json()
    assert user_a["organization_id"] == admin_a.organization_id

    # Register same email in Tenant B (must succeed because tenants are partitioned)
    resp_b = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Shared User B",
            "email": shared_email,
            "password": pwd,
            "organization_slug": "tenant-beta",
        },
    )
    assert resp_b.status_code == 201
    user_b = resp_b.json()
    assert user_b["organization_id"] == admin_b.organization_id

    # Duplicate in Tenant A must fail
    resp_dup = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Duplicate User A",
            "email": shared_email,
            "password": pwd,
            "organization_slug": "tenant-alpha",
        },
    )
    assert resp_dup.status_code == 400

