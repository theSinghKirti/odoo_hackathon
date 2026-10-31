from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_admin_create_product_with_variants(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    payload = {
        "name": "Brightloop CRM",
        "product_type": "software",
        "sales_price": "1000.00",
        "cost_price": "400.00",
        "notes": "Core cloud subscription product",
        "is_active": True,
        "variants": [
            {
                "attribute_name": "Brand",
                "attribute_value": "Odoo",
                "price_extra": "560.00",
                "sku": "BL-CRM-ODOO",
                "is_active": True,
            }
        ],
    }

    response = await client.post(
        "/api/v1/products",
        json=payload,
        headers=auth_header(admin),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Brightloop CRM"
    assert data["product_type"] == "software"
    assert Decimal(data["sales_price"]) == Decimal("1000.00")
    assert len(data["variants"]) == 1

    variant = data["variants"][0]
    assert variant["attribute_name"] == "Brand"
    assert variant["attribute_value"] == "Odoo"
    assert Decimal(variant["price_extra"]) == Decimal("560.00")
    # Base 1000 + Odoo Brand surcharge 560 = 1560.00
    assert Decimal(variant["effective_price"]) == Decimal("1560.00")


@pytest.mark.asyncio
async def test_add_variant_to_existing_product(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    # 1. Create base product without variants
    prod_resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Analytics Suite",
            "product_type": "software",
            "sales_price": "2000.00",
            "cost_price": "500.00",
        },
        headers=auth_header(admin),
    )
    assert prod_resp.status_code == 201
    product_id = prod_resp.json()["id"]

    # 2. Add Odoo brand variant with 560 surcharge
    var_resp = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json={
            "attribute_name": "Brand",
            "attribute_value": "Odoo",
            "price_extra": "560.00",
            "sku": "ANALYTICS-ODOO",
        },
        headers=auth_header(admin),
    )
    assert var_resp.status_code == 201
    variant_data = var_resp.json()
    assert variant_data["attribute_name"] == "Brand"
    assert variant_data["attribute_value"] == "Odoo"
    assert Decimal(variant_data["price_extra"]) == Decimal("560.00")
    assert Decimal(variant_data["effective_price"]) == Decimal("2560.00")


@pytest.mark.asyncio
async def test_duplicate_variant_rejected(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    prod_resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Inventory App",
            "product_type": "software",
            "sales_price": "1500.00",
        },
        headers=auth_header(admin),
    )
    product_id = prod_resp.json()["id"]

    variant_payload = {
        "attribute_name": "Brand",
        "attribute_value": "Odoo",
        "price_extra": "560.00",
    }

    # First addition succeeds
    r1 = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json=variant_payload,
        headers=auth_header(admin),
    )
    assert r1.status_code == 201

    # Second addition with identical attribute name & value returns 409 Conflict
    r2 = await client.post(
        f"/api/v1/products/{product_id}/variants",
        json=variant_payload,
        headers=auth_header(admin),
    )
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_staff_can_view_but_not_create_products(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]
    staff = seed_data["staff_a"]

    # Admin creates product
    await client.post(
        "/api/v1/products",
        json={"name": "Helpdesk Module", "product_type": "service", "sales_price": "800.00"},
        headers=auth_header(admin),
    )

    # Staff lists products -> 200 OK
    list_resp = await client.get("/api/v1/products", headers=auth_header(staff))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Staff attempts to create product -> 403 Forbidden
    create_resp = await client.post(
        "/api/v1/products",
        json={"name": "Illegal Product", "product_type": "software", "sales_price": "100.00"},
        headers=auth_header(staff),
    )
    assert create_resp.status_code == 403


@pytest.mark.asyncio
async def test_customer_forbidden_from_product_catalog_api(client: AsyncClient, seed_data: dict):
    customer = seed_data["customer_a"]
    resp = await client.get("/api/v1/products", headers=auth_header(customer))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_tenant_isolation_products_and_variants(client: AsyncClient, seed_data: dict):
    admin_a = seed_data["admin_a"]
    admin_b = seed_data["admin_b"]

    # Org A creates a product
    prod_a_resp = await client.post(
        "/api/v1/products",
        json={"name": "Org A Confidential Software", "product_type": "software", "sales_price": "5000.00"},
        headers=auth_header(admin_a),
    )
    prod_a_id = prod_a_resp.json()["id"]

    # Org B lists products: Org A product must NOT appear
    list_b_resp = await client.get("/api/v1/products", headers=auth_header(admin_b))
    assert list_b_resp.status_code == 200
    b_names = [p["name"] for p in list_b_resp.json()]
    assert "Org A Confidential Software" not in b_names

    # Org B cannot access Org A product by ID (returns 404)
    get_b_resp = await client.get(f"/api/v1/products/{prod_a_id}", headers=auth_header(admin_b))
    assert get_b_resp.status_code == 404

    # Org B cannot add a variant to Org A's product (returns 404)
    add_var_b = await client.post(
        f"/api/v1/products/{prod_a_id}/variants",
        json={"attribute_name": "Brand", "attribute_value": "Hack", "price_extra": "10.00"},
        headers=auth_header(admin_b),
    )
    assert add_var_b.status_code == 404


@pytest.mark.asyncio
async def test_product_filtering_and_addon_types(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # Create Software product
    await client.post(
        "/api/v1/products",
        json={"name": "Brightloop Invoicing", "product_type": "software", "sales_price": "1200.00"},
        headers=auth_header(admin),
    )
    # Create Addon product
    await client.post(
        "/api/v1/products",
        json={"name": "Extra 50GB Cloud Storage", "product_type": "addon", "sales_price": "300.00"},
        headers=auth_header(admin),
    )

    # Filter for addons
    addon_resp = await client.get("/api/v1/products?product_type=addon", headers=auth_header(admin))
    assert addon_resp.status_code == 200
    addons = addon_resp.json()
    assert len(addons) == 1
    assert addons[0]["name"] == "Extra 50GB Cloud Storage"
    assert addons[0]["product_type"] == "addon"

    # Search filter
    search_resp = await client.get("/api/v1/products?search=Invoicing", headers=auth_header(admin))
    assert search_resp.status_code == 200
    searched = search_resp.json()
    assert len(searched) == 1
    assert searched[0]["name"] == "Brightloop Invoicing"


@pytest.mark.asyncio
async def test_product_update_and_variant_update(client: AsyncClient, seed_data: dict):
    admin = seed_data["admin_a"]

    # 1. Create product with a variant
    prod_resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Point of Sale",
            "product_type": "software",
            "sales_price": "1000.00",
            "variants": [
                {"attribute_name": "Brand", "attribute_value": "Odoo", "price_extra": "560.00"}
            ],
        },
        headers=auth_header(admin),
    )
    prod = prod_resp.json()
    prod_id = prod["id"]
    var_id = prod["variants"][0]["id"]

    # 2. Update product sales_price from 1000 to 1200
    patch_prod = await client.patch(
        f"/api/v1/products/{prod_id}",
        json={"sales_price": "1200.00", "notes": "Updated pricing for Q4"},
        headers=auth_header(admin),
    )
    assert patch_prod.status_code == 200
    assert Decimal(patch_prod.json()["sales_price"]) == Decimal("1200.00")

    # 3. Update variant price_extra from 560 to 600
    patch_var = await client.patch(
        f"/api/v1/products/{prod_id}/variants/{var_id}",
        json={"price_extra": "600.00"},
        headers=auth_header(admin),
    )
    assert patch_var.status_code == 200
    assert Decimal(patch_var.json()["price_extra"]) == Decimal("600.00")
    # Base 1200 + Surcharge 600 = 1800.00
    assert Decimal(patch_var.json()["effective_price"]) == Decimal("1800.00")
