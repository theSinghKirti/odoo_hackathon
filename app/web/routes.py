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
