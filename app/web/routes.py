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
