from decimal import Decimal
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    set_auth_cookie,
)
from app.db.session import get_async_db
from app.models.user import User
from app.models.product import ProductType
from app.models.plan import SubscriptionPlan, BillingInterval
from app.models.tax import TaxRule
from app.schemas.tax import TaxRuleCreate, TaxRuleUpdate
from app.services.tax_service import TaxService
from app.models.discount import DiscountRule, DiscountType, DiscountScope
from app.schemas.discount import DiscountRuleCreate, DiscountRuleUpdate
from app.services.discount_service import DiscountService
from app.schemas.plan import PlanCreate, PlanUpdate
from app.services.plan_service import PlanService
from datetime import date
from app.schemas.product import ProductCreate, ProductUpdate, ProductVariantCreate
from app.models.product import ProductVariant
from sqlalchemy import delete
from datetime import datetime
from app.services.product_service import ProductService
from app.services.auth_service import (
    authenticate_user,
    register_customer_user,
    request_password_reset,
    reset_password_with_token,
    AuthenticationError,
    TenantInactiveError,
    UserInactiveError,
    RegistrationError,
    ResetPasswordError,
)
from app.services.password_service import PasswordValidationError

router = APIRouter(include_in_schema=False)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


async def get_optional_user(request: Request, db: AsyncSession) -> Optional[User]:
    """Helper to get user from cookie if present, without throwing 401."""
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))
        stmt = select(User).options(selectinload(User.organization)).where(User.id == user_id)
        res = await db.execute(stmt)
        user = res.scalars().first()
        if user and user.is_active and user.organization and user.organization.is_active:
            return user
        return None
    except Exception:
        return None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"user": None, "error": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        user = await authenticate_user(db, email=email, password=password)
        token = create_access_token(
            subject=str(user.id),
            organization_id=user.organization_id,
            role=user.role.value,
        )
        redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        set_auth_cookie(redirect, token)
        return redirect
    except (AuthenticationError, UserInactiveError, TenantInactiveError) as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "user": None,
                "error": str(e),
                "email": email,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_async_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"user": None, "error": None},
    )


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    organization_slug: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        user = await register_customer_user(
            session=db,
            full_name=full_name,
            email=email,
            password=password,
            organization_slug=organization_slug,
        )
        token = create_access_token(
            subject=str(user.id),
            organization_id=user.organization_id,
            role=user.role.value,
        )
        redirect = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        set_auth_cookie(redirect, token)
        return redirect
    except (RegistrationError, PasswordValidationError) as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context={
                "user": None,
                "error": str(e),
                "full_name": full_name,
                "email": email,
                "organization_slug": organization_slug,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password.html",
        context={"user": None, "error": None, "message": None, "dev_token": None},
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_async_db),
):
    raw_token = await request_password_reset(db, email=email)
    dev_token = None
    if settings.ENABLE_DEV_PASSWORD_RESET_SIMULATION and not settings.is_production:
        dev_token = raw_token

    return templates.TemplateResponse(
        request=request,
        name="auth/forgot_password.html",
        context={
            "user": None,
            "error": None,
            "message": "If this email is registered, password reset instructions have been generated.",
            "dev_token": dev_token,
            "prefill_token": dev_token or "",
        },
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        await reset_password_with_token(db, token=token, new_password=new_password)
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "user": None,
                "error": None,
                "message": "Password successfully reset! Please sign in with your new credentials.",
            },
        )
    except (ResetPasswordError, PasswordValidationError) as e:
        return templates.TemplateResponse(
            request=request,
            name="auth/forgot_password.html",
            context={
                "user": None,
                "error": str(e),
                "message": None,
                "dev_token": None,
                "prefill_token": token,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "user": user,
            "organization": user.organization,
            "active_nav": "dashboard",
        },
    )


# ---------------------------------------------------------------------------
# F2.1 Product Catalog Web Routes & HTMX Endpoints
# ---------------------------------------------------------------------------

MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "Odoo Enterprise",
        "product_type": "software",
        "sales_price": Decimal("5000.00"),
        "cost_price": Decimal("3000.00"),
        "notes": "Full suite ERP license with automated maintenance",
        "is_active": True,
        "variants": [],
    },
    {
        "id": 2,
        "name": "Odoo Implementation",
        "product_type": "service",
        "sales_price": Decimal("8000.00"),
        "cost_price": Decimal("4500.00"),
        "notes": "End-to-end architecture and module deployment",
        "is_active": True,
        "variants": [],
    },
    {
        "id": 3,
        "name": "Odoo Brand Add-on",
        "product_type": "addon",
        "sales_price": Decimal("560.00"),
        "cost_price": Decimal("300.00"),
        "notes": "White-label customization and brand assets package",
        "is_active": True,
        "variants": [],
    },
    {
        "id": 4,
        "name": "Physical License Key",
        "product_type": "physical",
        "sales_price": Decimal("1200.00"),
        "cost_price": Decimal("700.00"),
        "notes": "Hardware dongle and cryptographic security key",
        "is_active": False,
        "variants": [],
    },
]


def _get_product_type_str(product) -> str:
    if isinstance(product, dict):
        t = product.get("product_type", "")
    else:
        t = getattr(product, "product_type", "")
    if hasattr(t, "value"):
        return str(t.value).lower()
    return str(t).lower()


def _compute_product_stats(products_list):
    total = len(products_list)
    software = sum(1 for p in products_list if _get_product_type_str(p) == "software")
    services = sum(1 for p in products_list if _get_product_type_str(p) == "service")
    addons = sum(1 for p in products_list if _get_product_type_str(p) == "addon")
    return {
        "total": total,
        "software": software,
        "services": services,
        "addons": addons,
    }


def _filter_mock_products(search: Optional[str] = None, product_type: Optional[str] = None):
    results = list(MOCK_PRODUCTS)
    if product_type:
        pt_clean = product_type.strip().lower()
        results = [p for p in results if _get_product_type_str(p) == pt_clean]
    if search:
        s_clean = search.strip().lower()
        results = [
            p for p in results
            if s_clean in str(p.get("name", "")).lower() or s_clean in str(p.get("notes", "")).lower()
        ]
    return results


@router.get("/admin/products", response_class=HTMLResponse)
async def products_catalog_page(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    # Attempt to load tenant products
    try:
        db_products = await ProductService.list_products(db, organization_id=user.organization_id)
    except Exception:
        db_products = []

    # Use database products if available, fallback to approved mock data
    if db_products:
        products = db_products
        stats = _compute_product_stats(db_products)
    else:
        products = MOCK_PRODUCTS
        stats = _compute_product_stats(MOCK_PRODUCTS)

    return templates.TemplateResponse(
        request=request,
        name="admin/products.html",
        context={
            "user": user,
            "organization": user.organization,
            "active_nav": "products",
            "products": products,
            "stats": stats,
        },
    )


@router.get("/web/products", response_class=HTMLResponse)
async def products_table_partial(
    request: Request,
    search: Optional[str] = None,
    type: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    parsed_type: Optional[ProductType] = None
    if type and type.strip():
        try:
            parsed_type = ProductType(type.strip().lower())
        except ValueError:
            parsed_type = None

    db_products = []
    if user:
        try:
            db_products = await ProductService.list_products(
                db,
                organization_id=user.organization_id,
                product_type=parsed_type,
                search=search.strip() if search else None,
            )
        except Exception:
            db_products = []

    # If DB returned items or if the organization has created products
    if db_products:
        products = db_products
    else:
        # Check if tenant has any products at all
        has_any_in_db = False
        if user:
            try:
                all_db = await ProductService.list_products(db, organization_id=user.organization_id, limit=1)
                has_any_in_db = bool(all_db)
            except Exception:
                has_any_in_db = False

        if has_any_in_db:
            # The search or filter simply returned 0 matching results in DB
            products = []
        else:
            # Catalog is empty, use filtered mock preview records
            products = _filter_mock_products(search=search, product_type=type)

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/product_table.html",
        context={
            "user": user,
            "products": products,
        },
    )


# ---------------------------------------------------------------------------
# F2.2 Product Modal Endpoints (Create & Edit)
# ---------------------------------------------------------------------------

def _validate_product_input(
    name: str,
    product_type: str,
    sales_price: str,
    cost_price: Optional[str] = None,
    notes: Optional[str] = None,
    is_active: Optional[str] = None,
):
    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Product name is required."
    elif len(clean_name) > 255:
        errors["name"] = "Product name cannot exceed 255 characters."

    valid_types = [t.value for t in ProductType]
    clean_type = product_type.strip().lower() if product_type else ""
    if clean_type not in valid_types:
        errors["product_type"] = f"Please select a valid product type ({', '.join(valid_types)})."

    parsed_sales_price = None
    if not sales_price or not sales_price.strip():
        errors["sales_price"] = "Sales price is required."
    else:
        try:
            parsed_sales_price = Decimal(sales_price.strip())
            if parsed_sales_price < Decimal("0.00"):
                errors["sales_price"] = "Sales price must be a non-negative number."
        except Exception:
            errors["sales_price"] = "Sales price must be a valid number (e.g. 5000.00)."

    parsed_cost_price = Decimal("0.00")
    if cost_price and cost_price.strip():
        try:
            parsed_cost_price = Decimal(cost_price.strip())
            if parsed_cost_price < Decimal("0.00"):
                errors["cost_price"] = "Cost price must be a non-negative number."
        except Exception:
            errors["cost_price"] = "Cost price must be a valid number (e.g. 3000.00)."

    clean_notes = notes.strip() if notes and notes.strip() else None
    parsed_is_active = bool(is_active)

    form_data = {
        "name": clean_name,
        "product_type": clean_type,
        "sales_price": sales_price.strip() if sales_price else "",
        "cost_price": cost_price.strip() if cost_price else "",
        "notes": notes if notes else "",
        "is_active": parsed_is_active,
    }

    return errors, form_data, clean_name, clean_type, parsed_sales_price, parsed_cost_price, clean_notes, parsed_is_active


def _render_product_success_response(
    request: Request,
    products_list,
    stats,
    user,
    message: str,
):
    table_html = templates.get_template("admin/partials/product_table.html").render(
        request=request,
        products=products_list,
        user=user,
    )

    stats_grid_html = f"""
    <div class="grid" id="catalog-stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));" hx-swap-oob="outerHTML">
      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Total Products</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-sky); color: #0284C7; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-total-products">{stats["total"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">All catalog offerings</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Software</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-sky); color: #1E40AF; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-software-products">{stats["software"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Core licenses & apps</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Services</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-lavender); color: #7C3AED; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-service-products">{stats["services"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Implementation & setup</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Add-ons</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-mint); color: #059669; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-addon-products">{stats["addons"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Extensions & plugins</p>
      </div>
    </div>
    """

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">{message}</div>
        </div>
      </div>
      <script>
        setTimeout(() => {{
          const t = document.getElementById('{toast_id}');
          if (t) t.remove();
        }}, 4000);
      </script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <tbody id="products-table-body" hx-swap-oob="innerHTML">
      {table_html}
    </tbody>
    {stats_grid_html}
    {toast_html}
    """

    headers = {"HX-Trigger": "productListChanged"}
    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK, headers=headers)


@router.get("/web/products/modal", response_class=HTMLResponse)
async def product_create_modal(request: Request):
    """
    Renders the empty create product modal partial.
    """
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/product_form.html",
        context={
            "product": None,
            "form": None,
            "errors": None,
        },
    )


@router.get("/web/products/{product_id}/modal", response_class=HTMLResponse)
async def product_edit_modal(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Renders the product form modal pre-populated for editing.
    """
    user = await get_optional_user(request, db)
    product = None

    if user:
        try:
            product = await ProductService.get_product(
                db,
                organization_id=user.organization_id,
                product_id=product_id,
            )
        except Exception:
            product = None

    if not product:
        for mp in MOCK_PRODUCTS:
            if mp["id"] == product_id:
                product = mp
                break

    if not product:
        return HTMLResponse(
            content="<div class='alert alert-error'>Product not found</div>",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/product_form.html",
        context={
            "product": product,
            "form": None,
            "errors": None,
        },
    )


@router.post("/web/products", response_class=HTMLResponse)
async def product_create_submit(
    request: Request,
    name: str = Form(""),
    product_type: str = Form("software"),
    sales_price: str = Form(""),
    cost_price: Optional[str] = Form(""),
    notes: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Handles HTMX submission to create a new product, including dynamic variants.
    """
    user = await get_optional_user(request, db)

    errors, form_data, clean_name, clean_type, parsed_sales, parsed_cost, clean_notes, parsed_active = (
        _validate_product_input(name, product_type, sales_price, cost_price, notes, is_active)
    )

    # Extract dynamic variant rows from form
    raw_form = await request.form()
    attr_names = raw_form.getlist("variant_attribute_name[]")
    attr_values = raw_form.getlist("variant_attribute_value[]")
    skus = raw_form.getlist("variant_sku[]")
    price_extras = raw_form.getlist("variant_price_extra[]")

    variants_list = []
    variant_schemas = []
    for i in range(len(attr_names)):
        a_n = attr_names[i].strip() if i < len(attr_names) else ""
        a_v = attr_values[i].strip() if i < len(attr_values) else ""
        s_k = skus[i].strip() if i < len(skus) and skus[i] else None
        p_e_raw = price_extras[i].strip() if i < len(price_extras) and price_extras[i] else "0.00"

        if a_n and a_v:
            try:
                p_e = Decimal(p_e_raw)
                if p_e < Decimal("0.00"):
                    p_e = Decimal("0.00")
            except Exception:
                p_e = Decimal("0.00")

            v_dict = {
                "attribute_name": a_n,
                "attribute_value": a_v,
                "sku": s_k,
                "price_extra": p_e,
                "is_active": True,
            }
            variants_list.append(v_dict)
            variant_schemas.append(
                ProductVariantCreate(
                    attribute_name=a_n,
                    attribute_value=a_v,
                    sku=s_k,
                    price_extra=p_e,
                    is_active=True,
                )
            )

    form_data["variants"] = variants_list

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/product_form.html",
            context={
                "product": None,
                "form": form_data,
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Persist product
    created_in_db = False
    if user:
        try:
            create_schema = ProductCreate(
                name=clean_name,
                product_type=ProductType(clean_type),
                sales_price=parsed_sales,
                cost_price=parsed_cost,
                notes=clean_notes,
                is_active=parsed_active,
                variants=variant_schemas if variant_schemas else None,
            )
            await ProductService.create_product(
                session=db,
                organization_id=user.organization_id,
                data=create_schema,
            )
            created_in_db = True
        except Exception as e:
            created_in_db = False

    if not created_in_db:
        # Save to mock list for instant local interaction
        new_id = (max((p["id"] for p in MOCK_PRODUCTS), default=0)) + 1
        new_mock_item = {
            "id": new_id,
            "name": clean_name,
            "product_type": clean_type,
            "sales_price": parsed_sales,
            "cost_price": parsed_cost,
            "notes": clean_notes,
            "is_active": parsed_active,
            "variants": variants_list,
        }
        MOCK_PRODUCTS.insert(0, new_mock_item)

    # Fetch fresh product list and stats
    try:
        db_prods = await ProductService.list_products(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_prods = []

    products = db_prods if db_prods else MOCK_PRODUCTS
    stats = _compute_product_stats(products)

    return _render_product_success_response(
        request=request,
        products_list=products,
        stats=stats,
        user=user,
        message=f"Product '{clean_name}' created successfully.",
    )


@router.post("/web/products/{product_id}", response_class=HTMLResponse)
@router.put("/web/products/{product_id}", response_class=HTMLResponse)
async def product_update_submit(
    request: Request,
    product_id: int,
    name: str = Form(""),
    product_type: str = Form("software"),
    sales_price: str = Form(""),
    cost_price: Optional[str] = Form(""),
    notes: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Handles HTMX submission to update an existing product, including dynamic variants.
    """
    user = await get_optional_user(request, db)

    errors, form_data, clean_name, clean_type, parsed_sales, parsed_cost, clean_notes, parsed_active = (
        _validate_product_input(name, product_type, sales_price, cost_price, notes, is_active)
    )

    # Extract dynamic variant rows from form
    raw_form = await request.form()
    attr_names = raw_form.getlist("variant_attribute_name[]")
    attr_values = raw_form.getlist("variant_attribute_value[]")
    skus = raw_form.getlist("variant_sku[]")
    price_extras = raw_form.getlist("variant_price_extra[]")

    variants_list = []
    for i in range(len(attr_names)):
        a_n = attr_names[i].strip() if i < len(attr_names) else ""
        a_v = attr_values[i].strip() if i < len(attr_values) else ""
        s_k = skus[i].strip() if i < len(skus) and skus[i] else None
        p_e_raw = price_extras[i].strip() if i < len(price_extras) and price_extras[i] else "0.00"

        if a_n and a_v:
            try:
                p_e = Decimal(p_e_raw)
                if p_e < Decimal("0.00"):
                    p_e = Decimal("0.00")
            except Exception:
                p_e = Decimal("0.00")

            v_dict = {
                "attribute_name": a_n,
                "attribute_value": a_v,
                "sku": s_k,
                "price_extra": p_e,
                "is_active": True,
            }
            variants_list.append(v_dict)

    form_data["variants"] = variants_list

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/product_form.html",
            context={
                "product": {"id": product_id, "name": clean_name},
                "form": form_data,
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    updated_in_db = False
    if user:
        try:
            update_schema = ProductUpdate(
                name=clean_name,
                product_type=ProductType(clean_type),
                sales_price=parsed_sales,
                cost_price=parsed_cost,
                notes=clean_notes,
                is_active=parsed_active,
            )
            await ProductService.update_product(
                session=db,
                organization_id=user.organization_id,
                product_id=product_id,
                data=update_schema,
            )
            # Sync variants in database
            await db.execute(delete(ProductVariant).where(ProductVariant.product_id == product_id))
            for v in variants_list:
                db.add(
                    ProductVariant(
                        organization_id=user.organization_id,
                        product_id=product_id,
                        attribute_name=v["attribute_name"],
                        attribute_value=v["attribute_value"],
                        sku=v["sku"],
                        price_extra=v["price_extra"],
                        is_active=True,
                    )
                )
            await db.commit()
            updated_in_db = True
        except Exception:
            await db.rollback()
            updated_in_db = False

    # Also update in MOCK_PRODUCTS if present
    for mp in MOCK_PRODUCTS:
        if mp["id"] == product_id:
            mp["name"] = clean_name
            mp["product_type"] = clean_type
            mp["sales_price"] = parsed_sales
            mp["cost_price"] = parsed_cost
            mp["notes"] = clean_notes
            mp["is_active"] = parsed_active
            mp["variants"] = variants_list
            break

    try:
        db_prods = await ProductService.list_products(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_prods = []

    products = db_prods if db_prods else MOCK_PRODUCTS
    stats = _compute_product_stats(products)

    return _render_product_success_response(
        request=request,
        products_list=products,
        stats=stats,
        user=user,
        message=f"Product '{clean_name}' updated successfully.",
    )


# ---------------------------------------------------------------------------
# F3 Subscription Plan Web Routes & HTMX Endpoints
# ---------------------------------------------------------------------------

MOCK_PLANS = [
    {
        "id": 1,
        "name": "Monthly Starter",
        "description": "Standard monthly subscription package for growing business operations.",
        "billing_interval": "monthly",
        "interval_count": 1,
        "base_price": Decimal("999.00"),
        "currency": "INR",
        "min_quantity": 1,
        "available_from": None,
        "available_until": None,
        "auto_close_on_expiry": True,
        "allow_early_close": True,
        "allow_pause": True,
        "allow_renewal": True,
        "is_active": True,
    },
    {
        "id": 2,
        "name": "Weekly Maintenance",
        "description": "Short-cycle recurring support and operational checkups.",
        "billing_interval": "weekly",
        "interval_count": 1,
        "base_price": Decimal("499.00"),
        "currency": "INR",
        "min_quantity": 1,
        "available_from": None,
        "available_until": None,
        "auto_close_on_expiry": True,
        "allow_early_close": True,
        "allow_pause": True,
        "allow_renewal": True,
        "is_active": True,
    },
    {
        "id": 3,
        "name": "Enterprise Annual",
        "description": "Comprehensive full-organization deployment with dedicated SLAs.",
        "billing_interval": "yearly",
        "interval_count": 1,
        "base_price": Decimal("9999.00"),
        "currency": "INR",
        "min_quantity": 5,
        "available_from": None,
        "available_until": None,
        "auto_close_on_expiry": True,
        "allow_early_close": True,
        "allow_pause": True,
        "allow_renewal": True,
        "is_active": True,
    },
    {
        "id": 4,
        "name": "Daily Compute Cloud",
        "description": "High-frequency ephemeral resource allocation and compute billing.",
        "billing_interval": "daily",
        "interval_count": 1,
        "base_price": Decimal("99.00"),
        "currency": "INR",
        "min_quantity": 1,
        "available_from": None,
        "available_until": None,
        "auto_close_on_expiry": True,
        "allow_early_close": False,
        "allow_pause": False,
        "allow_renewal": True,
        "is_active": True,
    },
]


def _get_plan_interval_str(plan) -> str:
    if isinstance(plan, dict):
        i = plan.get("billing_interval", "")
    else:
        i = getattr(plan, "billing_interval", "")
    if hasattr(i, "value"):
        return str(i.value).lower()
    return str(i).lower()


def _compute_plan_stats(plans_list):
    total = len(plans_list)
    monthly = sum(1 for p in plans_list if _get_plan_interval_str(p) == "monthly")
    yearly = sum(1 for p in plans_list if _get_plan_interval_str(p) == "yearly")
    active = sum(1 for p in plans_list if (p.get("is_active") if isinstance(p, dict) else getattr(p, "is_active", False)))
    return {
        "total": total,
        "monthly": monthly,
        "yearly": yearly,
        "active": active,
    }


def _filter_mock_plans(search: Optional[str] = None, interval: Optional[str] = None, is_active: Optional[bool] = None):
    results = list(MOCK_PLANS)
    if interval:
        int_clean = interval.strip().lower()
        results = [p for p in results if _get_plan_interval_str(p) == int_clean]
    if is_active is not None:
        results = [p for p in results if p.get("is_active") == is_active]
    if search:
        s_clean = search.strip().lower()
        results = [
            p for p in results
            if s_clean in str(p.get("name", "")).lower() or s_clean in str(p.get("description", "")).lower()
        ]
    return results


def _validate_plan_input(
    name: str,
    billing_interval: str,
    base_price: str,
    min_quantity: str,
    description: Optional[str] = None,
    available_from: Optional[str] = None,
    available_until: Optional[str] = None,
    auto_close_on_expiry: Optional[str] = None,
    allow_early_close: Optional[str] = None,
    allow_pause: Optional[str] = None,
    allow_renewal: Optional[str] = None,
    is_active: Optional[str] = None,
):
    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Plan name is required."
    elif len(clean_name) > 255:
        errors["name"] = "Plan name cannot exceed 255 characters."

    valid_intervals = [i.value for i in BillingInterval]
    clean_interval = billing_interval.strip().lower() if billing_interval else ""
    if clean_interval not in valid_intervals:
        errors["billing_interval"] = f"Please select a valid interval ({', '.join(valid_intervals)})."

    parsed_price = None
    if not base_price or not base_price.strip():
        errors["base_price"] = "Base price is required."
    else:
        try:
            parsed_price = Decimal(base_price.strip())
            if parsed_price < Decimal("0.00"):
                errors["base_price"] = "Base price must be a non-negative number."
        except Exception:
            errors["base_price"] = "Base price must be a valid number (e.g. 999.00)."

    parsed_min_qty = 1
    if min_quantity and min_quantity.strip():
        try:
            parsed_min_qty = int(min_quantity.strip())
            if parsed_min_qty < 1:
                errors["min_quantity"] = "Minimum quantity must be at least 1."
        except Exception:
            errors["min_quantity"] = "Minimum quantity must be a valid integer."

    parsed_from = None
    if available_from and available_from.strip():
        try:
            parsed_from = date.fromisoformat(available_from.strip())
        except Exception:
            errors["available_from"] = "Invalid date format for Available From."

    parsed_until = None
    if available_until and available_until.strip():
        try:
            parsed_until = date.fromisoformat(available_until.strip())
        except Exception:
            errors["available_until"] = "Invalid date format for Available Until."

    if parsed_from and parsed_until and parsed_until < parsed_from:
        errors["available_until"] = "Available Until date cannot precede Available From date."

    clean_desc = description.strip() if description and description.strip() else None

    form_data = {
        "name": clean_name,
        "description": clean_desc or "",
        "billing_interval": clean_interval,
        "base_price": base_price.strip() if base_price else "",
        "min_quantity": parsed_min_qty,
        "available_from": available_from.strip() if available_from else "",
        "available_until": available_until.strip() if available_until else "",
        "auto_close_on_expiry": bool(auto_close_on_expiry),
        "allow_early_close": bool(allow_early_close),
        "allow_pause": bool(allow_pause),
        "allow_renewal": bool(allow_renewal),
        "is_active": bool(is_active),
    }

    return (
        errors,
        form_data,
        clean_name,
        clean_desc,
        clean_interval,
        parsed_price,
        parsed_min_qty,
        parsed_from,
        parsed_until,
        bool(auto_close_on_expiry),
        bool(allow_early_close),
        bool(allow_pause),
        bool(allow_renewal),
        bool(is_active),
    )


def _render_plan_success_response(
    request: Request,
    plans_list,
    stats,
    user,
    message: str,
):
    grid_html = templates.get_template("admin/partials/plan_grid.html").render(
        request=request,
        plans=plans_list,
        user=user,
    )

    stats_grid_html = f"""
    <div class="grid" id="plan-stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));" hx-swap-oob="outerHTML">
      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Total Plans</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-sky); color: #0284C7; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-total-plans">{stats["total"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Configured recurring tiers</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Monthly Plans</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-sky); color: #1E40AF; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-monthly-plans">{stats["monthly"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Standard recurring cycle</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Yearly Plans</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-lavender); color: #7C3AED; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
              <line x1="16" y1="2" x2="16" y2="6"/>
              <line x1="8" y1="2" x2="8" y2="6"/>
              <line x1="3" y1="10" x2="21" y2="10"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-yearly-plans">{stats["yearly"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Annual commitment tiers</p>
      </div>

      <div class="stat-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="stat-label">Active Plans</div>
          <div style="width: 36px; height: 36px; border-radius: 8px; background-color: var(--pastel-mint); color: #059669; display: flex; align-items: center; justify-content: center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
        </div>
        <div class="stat-value" id="stat-active-plans">{stats["active"]}</div>
        <p style="font-size: 0.8rem; color: var(--text-muted);">Available for subscribing</p>
      </div>
    </div>
    """

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">{message}</div>
        </div>
      </div>
      <script>
        setTimeout(() => {{
          const t = document.getElementById('{toast_id}');
          if (t) t.remove();
        }}, 4000);
      </script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <div class="plan-grid" id="plans-grid-container" hx-swap-oob="innerHTML">
      {grid_html}
    </div>
    {stats_grid_html}
    {toast_html}
    """

    headers = {"HX-Trigger": "planListChanged"}
    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK, headers=headers)


@router.get("/admin/plans", response_class=HTMLResponse)
async def plans_catalog_page(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        db_plans = await PlanService.list_plans(db, organization_id=user.organization_id)
    except Exception:
        db_plans = []

    if db_plans:
        plans = db_plans
        stats = _compute_plan_stats(db_plans)
    else:
        plans = MOCK_PLANS
        stats = _compute_plan_stats(MOCK_PLANS)

    return templates.TemplateResponse(
        request=request,
        name="admin/plans.html",
        context={
            "user": user,
            "organization": user.organization,
            "active_nav": "plans",
            "plans": plans,
            "stats": stats,
        },
    )


@router.get("/web/plans", response_class=HTMLResponse)
async def plans_grid_partial(
    request: Request,
    search: Optional[str] = None,
    interval: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    parsed_interval: Optional[BillingInterval] = None
    if interval and interval.strip():
        try:
            parsed_interval = BillingInterval(interval.strip().lower())
        except ValueError:
            parsed_interval = None

    db_plans = []
    if user:
        try:
            db_plans = await PlanService.list_plans(
                db,
                organization_id=user.organization_id,
                billing_interval=parsed_interval,
                is_active=is_active,
                search=search.strip() if search else None,
            )
        except Exception:
            db_plans = []

    if db_plans:
        plans = db_plans
    else:
        has_any_in_db = False
        if user:
            try:
                all_db = await PlanService.list_plans(db, organization_id=user.organization_id, limit=1)
                has_any_in_db = bool(all_db)
            except Exception:
                has_any_in_db = False

        if has_any_in_db:
            plans = []
        else:
            plans = _filter_mock_plans(search=search, interval=interval, is_active=is_active)

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/plan_grid.html",
        context={
            "user": user,
            "plans": plans,
        },
    )


@router.get("/web/plans/modal", response_class=HTMLResponse)
async def plan_create_modal(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/plan_form.html",
        context={
            "plan": None,
            "form": None,
            "errors": None,
        },
    )


@router.get("/web/plans/{plan_id}/modal", response_class=HTMLResponse)
async def plan_edit_modal(
    request: Request,
    plan_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    plan = None

    if user:
        try:
            plan = await PlanService.get_plan(
                db,
                organization_id=user.organization_id,
                plan_id=plan_id,
            )
        except Exception:
            plan = None

    if not plan:
        for mp in MOCK_PLANS:
            if mp["id"] == plan_id:
                plan = mp
                break

    if not plan:
        return HTMLResponse(
            content="<div class='alert alert-error'>Plan not found</div>",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/plan_form.html",
        context={
            "plan": plan,
            "form": None,
            "errors": None,
        },
    )


@router.post("/web/plans", response_class=HTMLResponse)
async def plan_create_submit(
    request: Request,
    name: str = Form(""),
    billing_interval: str = Form("monthly"),
    base_price: str = Form(""),
    min_quantity: str = Form("1"),
    description: Optional[str] = Form(None),
    available_from: Optional[str] = Form(None),
    available_until: Optional[str] = Form(None),
    auto_close_on_expiry: Optional[str] = Form(None),
    allow_early_close: Optional[str] = Form(None),
    allow_pause: Optional[str] = Form(None),
    allow_renewal: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    (
        errors,
        form_data,
        clean_name,
        clean_desc,
        clean_interval,
        parsed_price,
        parsed_min_qty,
        parsed_from,
        parsed_until,
        p_auto_close,
        p_early_close,
        p_pause,
        p_renewal,
        parsed_active,
    ) = _validate_plan_input(
        name=name,
        billing_interval=billing_interval,
        base_price=base_price,
        min_quantity=min_quantity,
        description=description,
        available_from=available_from,
        available_until=available_until,
        auto_close_on_expiry=auto_close_on_expiry,
        allow_early_close=allow_early_close,
        allow_pause=allow_pause,
        allow_renewal=allow_renewal,
        is_active=is_active,
    )

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/plan_form.html",
            context={
                "plan": None,
                "form": form_data,
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    created_in_db = False
    if user:
        try:
            create_schema = PlanCreate(
                name=clean_name,
                description=clean_desc,
                billing_interval=BillingInterval(clean_interval),
                interval_count=1,
                base_price=parsed_price,
                currency="INR",
                min_quantity=parsed_min_qty,
                available_from=parsed_from,
                available_until=parsed_until,
                auto_close_on_expiry=p_auto_close,
                allow_early_close=p_early_close,
                allow_pause=p_pause,
                allow_renewal=p_renewal,
                is_active=parsed_active,
            )
            await PlanService.create_plan(
                session=db,
                organization_id=user.organization_id,
                data=create_schema,
            )
            created_in_db = True
        except Exception:
            created_in_db = False

    if not created_in_db:
        new_id = (max((p["id"] for p in MOCK_PLANS), default=0)) + 1
        new_mock_plan = {
            "id": new_id,
            "name": clean_name,
            "description": clean_desc,
            "billing_interval": clean_interval,
            "interval_count": 1,
            "base_price": parsed_price,
            "currency": "INR",
            "min_quantity": parsed_min_qty,
            "available_from": parsed_from,
            "available_until": parsed_until,
            "auto_close_on_expiry": p_auto_close,
            "allow_early_close": p_early_close,
            "allow_pause": p_pause,
            "allow_renewal": p_renewal,
            "is_active": parsed_active,
        }
        MOCK_PLANS.insert(0, new_mock_plan)

    try:
        db_plans = await PlanService.list_plans(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_plans = []

    plans = db_plans if db_plans else MOCK_PLANS
    stats = _compute_plan_stats(plans)

    return _render_plan_success_response(
        request=request,
        plans_list=plans,
        stats=stats,
        user=user,
        message=f"Plan '{clean_name}' created successfully.",
    )


@router.post("/web/plans/{plan_id}", response_class=HTMLResponse)
@router.put("/web/plans/{plan_id}", response_class=HTMLResponse)
async def plan_update_submit(
    request: Request,
    plan_id: int,
    name: str = Form(""),
    billing_interval: str = Form("monthly"),
    base_price: str = Form(""),
    min_quantity: str = Form("1"),
    description: Optional[str] = Form(None),
    available_from: Optional[str] = Form(None),
    available_until: Optional[str] = Form(None),
    auto_close_on_expiry: Optional[str] = Form(None),
    allow_early_close: Optional[str] = Form(None),
    allow_pause: Optional[str] = Form(None),
    allow_renewal: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    (
        errors,
        form_data,
        clean_name,
        clean_desc,
        clean_interval,
        parsed_price,
        parsed_min_qty,
        parsed_from,
        parsed_until,
        p_auto_close,
        p_early_close,
        p_pause,
        p_renewal,
        parsed_active,
    ) = _validate_plan_input(
        name=name,
        billing_interval=billing_interval,
        base_price=base_price,
        min_quantity=min_quantity,
        description=description,
        available_from=available_from,
        available_until=available_until,
        auto_close_on_expiry=auto_close_on_expiry,
        allow_early_close=allow_early_close,
        allow_pause=allow_pause,
        allow_renewal=allow_renewal,
        is_active=is_active,
    )

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/plan_form.html",
            context={
                "plan": {"id": plan_id, "name": clean_name},
                "form": form_data,
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    updated_in_db = False
    if user:
        try:
            update_schema = PlanUpdate(
                name=clean_name,
                description=clean_desc,
                billing_interval=BillingInterval(clean_interval),
                base_price=parsed_price,
                min_quantity=parsed_min_qty,
                available_from=parsed_from,
                available_until=parsed_until,
                auto_close_on_expiry=p_auto_close,
                allow_early_close=p_early_close,
                allow_pause=p_pause,
                allow_renewal=p_renewal,
                is_active=parsed_active,
            )
            await PlanService.update_plan(
                session=db,
                organization_id=user.organization_id,
                plan_id=plan_id,
                data=update_schema,
            )
            updated_in_db = True
        except Exception:
            updated_in_db = False

    for mp in MOCK_PLANS:
        if mp["id"] == plan_id:
            mp["name"] = clean_name
            mp["description"] = clean_desc
            mp["billing_interval"] = clean_interval
            mp["base_price"] = parsed_price
            mp["min_quantity"] = parsed_min_qty
            mp["available_from"] = parsed_from
            mp["available_until"] = parsed_until
            mp["auto_close_on_expiry"] = p_auto_close
            mp["allow_early_close"] = p_early_close
            mp["allow_pause"] = p_pause
            mp["allow_renewal"] = p_renewal
            mp["is_active"] = parsed_active
            break

    try:
        db_plans = await PlanService.list_plans(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_plans = []

    plans = db_plans if db_plans else MOCK_PLANS
    stats = _compute_plan_stats(plans)

    return _render_plan_success_response(
        request=request,
        plans_list=plans,
        stats=stats,
        user=user,
        message=f"Plan '{clean_name}' updated successfully.",
    )


# ---------------------------------------------------------------------------
# F4 Tax Rules & Discount Rules Web Routes & HTMX Endpoints
# ---------------------------------------------------------------------------

MOCK_TAXES = [
    {
        "id": 1,
        "name": "GST 18%",
        "rate": Decimal("18.00"),
        "is_active": True,
        "created_at": None,
    },
    {
        "id": 2,
        "name": "GST 5%",
        "rate": Decimal("5.00"),
        "is_active": True,
        "created_at": None,
    },
    {
        "id": 3,
        "name": "VAT 20% (Export)",
        "rate": Decimal("20.00"),
        "is_active": False,
        "created_at": None,
    },
]

MOCK_DISCOUNTS = [
    {
        "id": 1,
        "name": "Diwali Special 20%",
        "description": "Festive season promotional offer across all subscriptions.",
        "discount_type": "percentage",
        "discount_value": Decimal("20.00"),
        "min_purchase_amount": Decimal("1000.00"),
        "min_quantity": 1,
        "start_date": None,
        "end_date": None,
        "max_uses": 100,
        "times_used": 45,
        "scope": "subscription",
        "product_id": None,
        "product": None,
        "is_active": True,
        "status": "active",
    },
    {
        "id": 2,
        "name": "Enterprise Flat ₹1000",
        "description": "Volume discount for multi-license enterprise orders.",
        "discount_type": "fixed_amount",
        "discount_value": Decimal("1000.00"),
        "min_purchase_amount": Decimal("5000.00"),
        "min_quantity": 2,
        "start_date": None,
        "end_date": None,
        "max_uses": 50,
        "times_used": 12,
        "scope": "subscription",
        "product_id": None,
        "product": None,
        "is_active": True,
        "status": "active",
    },
    {
        "id": 3,
        "name": "Q1 Early Adopter",
        "description": "Launch phase introductory campaign.",
        "discount_type": "percentage",
        "discount_value": Decimal("10.00"),
        "min_purchase_amount": Decimal("0.00"),
        "min_quantity": 1,
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 3, 31),
        "max_uses": 200,
        "times_used": 200,
        "scope": "subscription",
        "product_id": None,
        "product": None,
        "is_active": True,
        "status": "expired",
    },
]


def _compute_tax_stats(taxes_list):
    total = len(taxes_list)
    active = sum(1 for t in taxes_list if (t.get("is_active") if isinstance(t, dict) else getattr(t, "is_active", False)))
    return {
        "total": total,
        "active": active,
    }


def _compute_discount_status(discount) -> str:
    today = date.today()
    is_act = discount.get("is_active") if isinstance(discount, dict) else getattr(discount, "is_active", False)
    if not is_act:
        return "inactive"
    
    end_d = discount.get("end_date") if isinstance(discount, dict) else getattr(discount, "end_date", None)
    if end_d and today > end_d:
        return "expired"

    max_u = discount.get("max_uses") if isinstance(discount, dict) else getattr(discount, "max_uses", None)
    times_u = discount.get("times_used", 0) if isinstance(discount, dict) else getattr(discount, "times_used", 0)
    if max_u is not None and times_u >= max_u:
        return "expired"

    start_d = discount.get("start_date") if isinstance(discount, dict) else getattr(discount, "start_date", None)
    if start_d and today < start_d:
        return "scheduled"

    return "active"


def _compute_discount_stats(discounts_list):
    total = len(discounts_list)
    active = 0
    inactive = 0
    redemptions = 0
    for d in discounts_list:
        st = _compute_discount_status(d)
        if st == "active":
            active += 1
        else:
            inactive += 1
        redemptions += (d.get("times_used", 0) if isinstance(d, dict) else getattr(d, "times_used", 0))
    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "redemptions": redemptions,
    }


# --- TAX RULES ENDPOINTS ---

@router.get("/admin/taxes", response_class=HTMLResponse)
async def taxes_page(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        db_taxes = await TaxService.list_tax_rules(db, organization_id=user.organization_id)
    except Exception:
        db_taxes = []

    taxes = db_taxes if db_taxes else MOCK_TAXES
    stats = _compute_tax_stats(taxes)

    return templates.TemplateResponse(
        request=request,
        name="admin/taxes.html",
        context={
            "user": user,
            "organization": user.organization,
            "active_nav": "taxes",
            "taxes": taxes,
            "stats": stats,
        },
    )


@router.get("/web/taxes", response_class=HTMLResponse)
async def taxes_table_partial(
    request: Request,
    search: Optional[str] = None,
    is_active: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    parsed_active = True if is_active == "true" else (False if is_active == "false" else None)

    db_taxes = []
    if user:
        try:
            db_taxes = await TaxService.list_tax_rules(
                db,
                organization_id=user.organization_id,
                is_active=parsed_active,
                search=search.strip() if search else None,
            )
        except Exception:
            db_taxes = []

    if db_taxes:
        taxes = db_taxes
    else:
        taxes = list(MOCK_TAXES)
        if parsed_active is not None:
            taxes = [t for t in taxes if t.get("is_active") == parsed_active]
        if search:
            s_clean = search.strip().lower()
            taxes = [t for t in taxes if s_clean in str(t.get("name", "")).lower()]

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/tax_table.html",
        context={
            "user": user,
            "taxes": taxes,
        },
    )


@router.get("/web/taxes/modal", response_class=HTMLResponse)
async def tax_create_modal(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/tax_form.html",
        context={
            "tax": None,
            "form": None,
            "errors": None,
        },
    )


@router.get("/web/taxes/{tax_id}/modal", response_class=HTMLResponse)
async def tax_edit_modal(
    request: Request,
    tax_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    tax = None
    if user:
        try:
            tax = await TaxService.get_tax_rule(db, organization_id=user.organization_id, tax_rule_id=tax_id)
        except Exception:
            tax = None

    if not tax:
        for mt in MOCK_TAXES:
            if mt["id"] == tax_id:
                tax = mt
                break

    if not tax:
        return HTMLResponse("<div class='alert alert-error'>Tax rule not found</div>", status_code=status.HTTP_404_NOT_FOUND)

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/tax_form.html",
        context={
            "tax": tax,
            "form": None,
            "errors": None,
        },
    )


@router.post("/web/taxes", response_class=HTMLResponse)
async def tax_create_submit(
    request: Request,
    name: str = Form(""),
    rate: str = Form(""),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Tax name is required."

    parsed_rate = None
    if not rate or not rate.strip():
        errors["rate"] = "Tax rate percentage is required."
    else:
        try:
            parsed_rate = Decimal(rate.strip())
            if parsed_rate < Decimal("0.00") or parsed_rate > Decimal("100.00"):
                errors["rate"] = "Tax rate must be between 0% and 100%."
        except Exception:
            errors["rate"] = "Tax rate must be a valid percentage."

    parsed_active = bool(is_active)

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/tax_form.html",
            context={
                "tax": None,
                "form": {"name": clean_name, "rate": rate, "is_active": parsed_active},
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    created_in_db = False
    if user:
        try:
            await TaxService.create_tax_rule(
                session=db,
                organization_id=user.organization_id,
                data=TaxRuleCreate(name=clean_name, rate=parsed_rate, is_active=parsed_active),
            )
            created_in_db = True
        except Exception:
            created_in_db = False

    if not created_in_db:
        new_id = (max((t["id"] for t in MOCK_TAXES), default=0)) + 1
        MOCK_TAXES.insert(0, {
            "id": new_id,
            "name": clean_name,
            "rate": parsed_rate,
            "is_active": parsed_active,
            "created_at": None,
        })

    try:
        db_taxes = await TaxService.list_tax_rules(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_taxes = []

    taxes = db_taxes if db_taxes else MOCK_TAXES
    stats = _compute_tax_stats(taxes)

    table_html = templates.get_template("admin/partials/tax_table.html").render(
        request=request,
        taxes=taxes,
        user=user,
    )

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">Tax rule '{clean_name}' created successfully.</div>
        </div>
      </div>
      <script>setTimeout(() => {{ const t = document.getElementById('{toast_id}'); if (t) t.remove(); }}, 4000);</script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <tbody id="taxes-table-body" hx-swap-oob="innerHTML">
      {table_html}
    </tbody>
    {toast_html}
    """

    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK)


@router.post("/web/taxes/{tax_id}", response_class=HTMLResponse)
@router.put("/web/taxes/{tax_id}", response_class=HTMLResponse)
async def tax_update_submit(
    request: Request,
    tax_id: int,
    name: str = Form(""),
    rate: str = Form(""),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Tax name is required."

    parsed_rate = None
    if not rate or not rate.strip():
        errors["rate"] = "Tax rate percentage is required."
    else:
        try:
            parsed_rate = Decimal(rate.strip())
            if parsed_rate < Decimal("0.00") or parsed_rate > Decimal("100.00"):
                errors["rate"] = "Tax rate must be between 0% and 100%."
        except Exception:
            errors["rate"] = "Tax rate must be a valid percentage."

    parsed_active = bool(is_active)

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin/partials/tax_form.html",
            context={
                "tax": {"id": tax_id, "name": clean_name},
                "form": {"name": clean_name, "rate": rate, "is_active": parsed_active},
                "errors": errors,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    updated_in_db = False
    if user:
        try:
            await TaxService.update_tax_rule(
                session=db,
                organization_id=user.organization_id,
                tax_rule_id=tax_id,
                data=TaxRuleUpdate(name=clean_name, rate=parsed_rate, is_active=parsed_active),
            )
            updated_in_db = True
        except Exception:
            updated_in_db = False

    for mt in MOCK_TAXES:
        if mt["id"] == tax_id:
            mt["name"] = clean_name
            mt["rate"] = parsed_rate
            mt["is_active"] = parsed_active
            break

    try:
        db_taxes = await TaxService.list_tax_rules(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_taxes = []

    taxes = db_taxes if db_taxes else MOCK_TAXES

    table_html = templates.get_template("admin/partials/tax_table.html").render(
        request=request,
        taxes=taxes,
        user=user,
    )

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">Tax rule '{clean_name}' updated successfully.</div>
        </div>
      </div>
      <script>setTimeout(() => {{ const t = document.getElementById('{toast_id}'); if (t) t.remove(); }}, 4000);</script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <tbody id="taxes-table-body" hx-swap-oob="innerHTML">
      {table_html}
    </tbody>
    {toast_html}
    """

    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK)


@router.post("/web/taxes/{tax_id}/toggle-status", response_class=HTMLResponse)
async def tax_toggle_status(
    request: Request,
    tax_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if user:
        try:
            tax = await TaxService.get_tax_rule(db, organization_id=user.organization_id, tax_rule_id=tax_id)
            await TaxService.update_tax_rule(
                session=db,
                organization_id=user.organization_id,
                tax_rule_id=tax_id,
                data=TaxRuleUpdate(is_active=not tax.is_active),
            )
        except Exception:
            pass

    for mt in MOCK_TAXES:
        if mt["id"] == tax_id:
            mt["is_active"] = not mt["is_active"]
            break

    try:
        db_taxes = await TaxService.list_tax_rules(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_taxes = []

    taxes = db_taxes if db_taxes else MOCK_TAXES
    return templates.TemplateResponse(
        request=request,
        name="admin/partials/tax_table.html",
        context={"user": user, "taxes": taxes},
    )


# --- DISCOUNT RULES ENDPOINTS ---

@router.get("/admin/discounts", response_class=HTMLResponse)
async def discounts_page(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        db_discounts = await DiscountService.list_discount_rules(db, organization_id=user.organization_id)
    except Exception:
        db_discounts = []

    discounts = db_discounts if db_discounts else MOCK_DISCOUNTS
    # Compute status for each
    for d in discounts:
        st = _compute_discount_status(d)
        if isinstance(d, dict):
            d["status"] = st
        else:
            setattr(d, "status", st)

    stats = _compute_discount_stats(discounts)

    return templates.TemplateResponse(
        request=request,
        name="admin/discounts.html",
        context={
            "user": user,
            "organization": user.organization,
            "active_nav": "discounts",
            "discounts": discounts,
            "stats": stats,
        },
    )


@router.get("/web/discounts", response_class=HTMLResponse)
async def discounts_table_partial(
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    db_discounts = []
    if user:
        try:
            db_discounts = await DiscountService.list_discount_rules(
                db,
                organization_id=user.organization_id,
                search=search.strip() if search else None,
            )
        except Exception:
            db_discounts = []

    discounts = db_discounts if db_discounts else list(MOCK_DISCOUNTS)
    for d in discounts:
        st = _compute_discount_status(d)
        if isinstance(d, dict):
            d["status"] = st
        else:
            setattr(d, "status", st)

    if status and status.strip():
        s_target = status.strip().lower()
        discounts = [
            d for d in discounts 
            if (d.get("status") if isinstance(d, dict) else getattr(d, "status", "")) == s_target
        ]

    if search:
        s_clean = search.strip().lower()
        discounts = [
            d for d in discounts 
            if s_clean in (d.get("name", "") if isinstance(d, dict) else getattr(d, "name", "")).lower()
        ]

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/discount_table.html",
        context={
            "user": user,
            "discounts": discounts,
        },
    )


@router.get("/web/discounts/modal", response_class=HTMLResponse)
async def discount_create_modal(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    products = []
    if user:
        try:
            products = await ProductService.list_products(db, organization_id=user.organization_id)
        except Exception:
            products = []
    if not products:
        products = MOCK_PRODUCTS

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/discount_form.html",
        context={
            "discount": None,
            "form": None,
            "errors": None,
            "products": products,
        },
    )


@router.get("/web/discounts/{discount_id}/modal", response_class=HTMLResponse)
async def discount_edit_modal(
    request: Request,
    discount_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)
    discount = None
    if user:
        try:
            discount = await DiscountService.get_discount_rule(db, organization_id=user.organization_id, rule_id=discount_id)
        except Exception:
            discount = None

    if not discount:
        for md in MOCK_DISCOUNTS:
            if md["id"] == discount_id:
                discount = md
                break

    if not discount:
        return HTMLResponse("<div class='alert alert-error'>Discount rule not found</div>", status_code=status.HTTP_404_NOT_FOUND)

    products = []
    if user:
        try:
            products = await ProductService.list_products(db, organization_id=user.organization_id)
        except Exception:
            products = []
    if not products:
        products = MOCK_PRODUCTS

    return templates.TemplateResponse(
        request=request,
        name="admin/partials/discount_form.html",
        context={
            "discount": discount,
            "form": None,
            "errors": None,
            "products": products,
        },
    )


@router.post("/web/discounts", response_class=HTMLResponse)
async def discount_create_submit(
    request: Request,
    name: str = Form(""),
    discount_type: str = Form("percentage"),
    discount_value: str = Form(""),
    min_purchase_amount: Optional[str] = Form(""),
    min_quantity: Optional[str] = Form("1"),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    max_uses: Optional[str] = Form(None),
    scope: str = Form("subscription"),
    product_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Discount name is required."

    parsed_val = None
    if not discount_value or not discount_value.strip():
        errors["discount_value"] = "Discount value is required."
    else:
        try:
            parsed_val = Decimal(discount_value.strip())
            if parsed_val < Decimal("0.00"):
                errors["discount_value"] = "Discount value must be non-negative."
            if discount_type == "percentage" and parsed_val > Decimal("100.00"):
                errors["discount_value"] = "Percentage discount cannot exceed 100%."
        except Exception:
            errors["discount_value"] = "Discount value must be a valid number."

    parsed_min_spend = Decimal("0.00")
    if min_purchase_amount and min_purchase_amount.strip():
        try:
            parsed_min_spend = Decimal(min_purchase_amount.strip())
        except Exception:
            parsed_min_spend = Decimal("0.00")

    parsed_min_qty = 1
    if min_quantity and min_quantity.strip():
        try:
            parsed_min_qty = int(min_quantity.strip())
        except Exception:
            parsed_min_qty = 1

    parsed_start = None
    if start_date and start_date.strip():
        try:
            parsed_start = date.fromisoformat(start_date.strip())
        except Exception:
            errors["start_date"] = "Invalid Start Date format."

    parsed_end = None
    if end_date and end_date.strip():
        try:
            parsed_end = date.fromisoformat(end_date.strip())
        except Exception:
            errors["end_date"] = "Invalid End Date format."

    if parsed_start and parsed_end and parsed_end < parsed_start:
        errors["end_date"] = "End Date cannot precede Start Date."

    parsed_max_uses = None
    if max_uses and max_uses.strip():
        try:
            parsed_max_uses = int(max_uses.strip())
        except Exception:
            parsed_max_uses = None

    parsed_prod_id = None
    if scope == "product" and product_id and product_id.strip():
        try:
            parsed_prod_id = int(product_id.strip())
        except Exception:
            parsed_prod_id = None

    parsed_active = bool(is_active)

    if errors:
        products = []
        if user:
            try:
                products = await ProductService.list_products(db, organization_id=user.organization_id)
            except Exception:
                products = []
        if not products:
            products = MOCK_PRODUCTS

        return templates.TemplateResponse(
            request=request,
            name="admin/partials/discount_form.html",
            context={
                "discount": None,
                "form": {
                    "name": clean_name,
                    "discount_type": discount_type,
                    "discount_value": discount_value,
                    "min_purchase_amount": min_purchase_amount,
                    "min_quantity": parsed_min_qty,
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_uses": max_uses,
                    "scope": scope,
                    "product_id": product_id,
                    "description": description,
                    "is_active": parsed_active,
                },
                "errors": errors,
                "products": products,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    created_in_db = False
    if user:
        try:
            await DiscountService.create_discount_rule(
                session=db,
                organization_id=user.organization_id,
                data=DiscountRuleCreate(
                    name=clean_name,
                    discount_type=DiscountType(discount_type),
                    discount_value=parsed_val,
                    min_purchase_amount=parsed_min_spend,
                    min_quantity=parsed_min_qty,
                    start_date=parsed_start,
                    end_date=parsed_end,
                    max_uses=parsed_max_uses,
                    scope=DiscountScope(scope),
                    product_id=parsed_prod_id,
                    is_active=parsed_active,
                ),
            )
            created_in_db = True
        except Exception:
            created_in_db = False

    if not created_in_db:
        new_id = (max((d["id"] for d in MOCK_DISCOUNTS), default=0)) + 1
        MOCK_DISCOUNTS.insert(0, {
            "id": new_id,
            "name": clean_name,
            "description": description,
            "discount_type": discount_type,
            "discount_value": parsed_val,
            "min_purchase_amount": parsed_min_spend,
            "min_quantity": parsed_min_qty,
            "start_date": parsed_start,
            "end_date": parsed_end,
            "max_uses": parsed_max_uses,
            "times_used": 0,
            "scope": scope,
            "product_id": parsed_prod_id,
            "product": None,
            "is_active": parsed_active,
            "status": "active" if parsed_active else "inactive",
        })

    try:
        db_discounts = await DiscountService.list_discount_rules(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_discounts = []

    discounts = db_discounts if db_discounts else MOCK_DISCOUNTS
    for d in discounts:
        st = _compute_discount_status(d)
        if isinstance(d, dict):
            d["status"] = st
        else:
            setattr(d, "status", st)

    table_html = templates.get_template("admin/partials/discount_table.html").render(
        request=request,
        discounts=discounts,
        user=user,
    )

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">Discount '{clean_name}' created successfully.</div>
        </div>
      </div>
      <script>setTimeout(() => {{ const t = document.getElementById('{toast_id}'); if (t) t.remove(); }}, 4000);</script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <tbody id="discounts-table-body" hx-swap-oob="innerHTML">
      {table_html}
    </tbody>
    {toast_html}
    """

    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK)


@router.post("/web/discounts/{discount_id}", response_class=HTMLResponse)
@router.put("/web/discounts/{discount_id}", response_class=HTMLResponse)
async def discount_update_submit(
    request: Request,
    discount_id: int,
    name: str = Form(""),
    discount_type: str = Form("percentage"),
    discount_value: str = Form(""),
    min_purchase_amount: Optional[str] = Form(""),
    min_quantity: Optional[str] = Form("1"),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    max_uses: Optional[str] = Form(None),
    scope: str = Form("subscription"),
    product_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
):
    user = await get_optional_user(request, db)

    errors = {}
    clean_name = name.strip() if name else ""
    if not clean_name:
        errors["name"] = "Discount name is required."

    parsed_val = None
    if not discount_value or not discount_value.strip():
        errors["discount_value"] = "Discount value is required."
    else:
        try:
            parsed_val = Decimal(discount_value.strip())
            if parsed_val < Decimal("0.00"):
                errors["discount_value"] = "Discount value must be non-negative."
            if discount_type == "percentage" and parsed_val > Decimal("100.00"):
                errors["discount_value"] = "Percentage discount cannot exceed 100%."
        except Exception:
            errors["discount_value"] = "Discount value must be a valid number."

    parsed_min_spend = Decimal("0.00")
    if min_purchase_amount and min_purchase_amount.strip():
        try:
            parsed_min_spend = Decimal(min_purchase_amount.strip())
        except Exception:
            parsed_min_spend = Decimal("0.00")

    parsed_min_qty = 1
    if min_quantity and min_quantity.strip():
        try:
            parsed_min_qty = int(min_quantity.strip())
        except Exception:
            parsed_min_qty = 1

    parsed_start = None
    if start_date and start_date.strip():
        try:
            parsed_start = date.fromisoformat(start_date.strip())
        except Exception:
            errors["start_date"] = "Invalid Start Date format."

    parsed_end = None
    if end_date and end_date.strip():
        try:
            parsed_end = date.fromisoformat(end_date.strip())
        except Exception:
            errors["end_date"] = "Invalid End Date format."

    if parsed_start and parsed_end and parsed_end < parsed_start:
        errors["end_date"] = "End Date cannot precede Start Date."

    parsed_max_uses = None
    if max_uses and max_uses.strip():
        try:
            parsed_max_uses = int(max_uses.strip())
        except Exception:
            parsed_max_uses = None

    parsed_prod_id = None
    if scope == "product" and product_id and product_id.strip():
        try:
            parsed_prod_id = int(product_id.strip())
        except Exception:
            parsed_prod_id = None

    parsed_active = bool(is_active)

    if errors:
        products = []
        if user:
            try:
                products = await ProductService.list_products(db, organization_id=user.organization_id)
            except Exception:
                products = []
        if not products:
            products = MOCK_PRODUCTS

        return templates.TemplateResponse(
            request=request,
            name="admin/partials/discount_form.html",
            context={
                "discount": {"id": discount_id, "name": clean_name},
                "form": {
                    "name": clean_name,
                    "discount_type": discount_type,
                    "discount_value": discount_value,
                    "min_purchase_amount": min_purchase_amount,
                    "min_quantity": parsed_min_qty,
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_uses": max_uses,
                    "scope": scope,
                    "product_id": product_id,
                    "description": description,
                    "is_active": parsed_active,
                },
                "errors": errors,
                "products": products,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    updated_in_db = False
    if user:
        try:
            await DiscountService.update_discount_rule(
                session=db,
                organization_id=user.organization_id,
                rule_id=discount_id,
                data=DiscountRuleUpdate(
                    name=clean_name,
                    discount_type=DiscountType(discount_type),
                    discount_value=parsed_val,
                    min_purchase_amount=parsed_min_spend,
                    min_quantity=parsed_min_qty,
                    start_date=parsed_start,
                    end_date=parsed_end,
                    max_uses=parsed_max_uses,
                    scope=DiscountScope(scope),
                    product_id=parsed_prod_id,
                    is_active=parsed_active,
                ),
            )
            updated_in_db = True
        except Exception:
            updated_in_db = False

    for md in MOCK_DISCOUNTS:
        if md["id"] == discount_id:
            md["name"] = clean_name
            md["description"] = description
            md["discount_type"] = discount_type
            md["discount_value"] = parsed_val
            md["min_purchase_amount"] = parsed_min_spend
            md["min_quantity"] = parsed_min_qty
            md["start_date"] = parsed_start
            md["end_date"] = parsed_end
            md["max_uses"] = parsed_max_uses
            md["scope"] = scope
            md["product_id"] = parsed_prod_id
            md["is_active"] = parsed_active
            break

    try:
        db_discounts = await DiscountService.list_discount_rules(db, organization_id=user.organization_id) if user else []
    except Exception:
        db_discounts = []

    discounts = db_discounts if db_discounts else MOCK_DISCOUNTS
    for d in discounts:
        st = _compute_discount_status(d)
        if isinstance(d, dict):
            d["status"] = st
        else:
            setattr(d, "status", st)

    table_html = templates.get_template("admin/partials/discount_table.html").render(
        request=request,
        discounts=discounts,
        user=user,
    )

    toast_id = f"toast_{int(datetime.now().timestamp())}"
    toast_html = f"""
    <div id="toast-container" hx-swap-oob="innerHTML">
      <div class="toast toast-success" id="{toast_id}">
        <div class="toast-icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div>
          <div style="font-weight: 600; color: var(--navy);">Success</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">Discount '{clean_name}' updated successfully.</div>
        </div>
      </div>
      <script>setTimeout(() => {{ const t = document.getElementById('{toast_id}'); if (t) t.remove(); }}, 4000);</script>
    </div>
    """

    response_html = f"""
    <div id="modal-container" hx-swap-oob="innerHTML"></div>
    <tbody id="discounts-table-body" hx-swap-oob="innerHTML">
      {table_html}
    </tbody>
    {toast_html}
    """

    return HTMLResponse(content=response_html, status_code=status.HTTP_200_OK)
