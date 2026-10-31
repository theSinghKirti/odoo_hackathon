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
