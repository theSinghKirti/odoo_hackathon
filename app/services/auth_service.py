from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
import secrets
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.customer import Customer
from app.models.token import PasswordResetToken
from app.services.password_service import (
    hash_password,
    validate_password_policy,
    verify_password,
    PasswordValidationError,
)

logger = logging.getLogger(__name__)

# Development-only in-memory token store for test inspection
DEV_SIMULATED_EMAILS = []


class AuthenticationError(Exception):
    """Raised for authentication failures."""
    pass


class TenantInactiveError(AuthenticationError):
    """Raised when the user's organization is suspended or inactive."""
    pass


class UserInactiveError(AuthenticationError):
    """Raised when the user account is inactive."""
    pass


class RegistrationError(Exception):
    """Raised when registration cannot be completed."""
    pass


class ResetPasswordError(Exception):
    """Raised when password reset token is invalid or expired."""
    pass


def _hash_token(plain_token: str) -> str:
    """Computes SHA-256 digest of a reset token for secure persistence."""
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User:
    """
    Authenticates a user by email and password.
    Enforces active user and active organization verification.
    """
    stmt = (
        select(User)
        .options(selectinload(User.organization))
        .where(User.email == email.lower().strip())
    )
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthenticationError("Invalid email or password.")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise UserInactiveError("User account is inactive. Please contact your administrator.")

    if not user.organization or not user.organization.is_active:
        raise TenantInactiveError("Organization account is inactive. Access denied.")

    return user


async def register_customer_user(
    session: AsyncSession,
    full_name: str,
    email: str,
    password: str,
    organization_slug: Optional[str] = None,
) -> User:
    """
    Public registration endpoint: Creates a Customer role account only.
    Admins and Staff can NEVER be created through public customer registration.
    """
    # 1. Validate password policy
    validate_password_policy(password)

    # 2. Resolve organization
    slug = organization_slug or settings.INITIAL_TENANT_SLUG
    stmt_org = select(Organization).where(Organization.slug == slug)
    res_org = await session.execute(stmt_org)
    organization = res_org.scalars().first()

    if not organization:
        raise RegistrationError(f"Target organization '{slug}' not found.")

    if not organization.is_active:
        raise RegistrationError("Cannot register with an inactive organization.")

    # 3. Check for existing user in this tenant
    email_clean = email.lower().strip()
    stmt_user = select(User).where(
        User.organization_id == organization.id,
        User.email == email_clean,
    )
    res_user = await session.execute(stmt_user)
    if res_user.scalars().first():
        raise RegistrationError("An account with this email already exists in this organization.")

    # 4. Create user record with Customer role
    user = User(
        organization_id=organization.id,
        full_name=full_name.strip(),
        email=email_clean,
        password_hash=hash_password(password),
        role=UserRole.CUSTOMER,
        is_active=True,
        is_verified=False,
    )
    session.add(user)
    await session.flush()  # obtain user.id

    # 5. Create associated Customer entity
    customer = Customer(
        organization_id=organization.id,
        user_id=user.id,
        name=full_name.strip(),
        email=email_clean,
        is_active=True,
    )
    session.add(customer)
    await session.commit()
    await session.refresh(user)

    return user


async def register_admin_user(
    session: AsyncSession,
    organization_name: str,
    full_name: str,
    email: str,
    password: str,
    organization_slug: Optional[str] = None,
) -> User:
    """
    Onboarding registration endpoint for Admin / Company accounts.
    Creates a new Organization (tenant) and the primary Admin user.
    """
    # 1. Validate password policy
    validate_password_policy(password)

    org_name_clean = organization_name.strip()
    if not org_name_clean:
        raise RegistrationError("Organization name is required.")

    # 2. Derive / validate organization slug
    if organization_slug and organization_slug.strip():
        slug = re.sub(r"[^a-z0-9\-]+", "-", organization_slug.strip().lower()).strip("-")
    else:
        slug = re.sub(r"[^a-z0-9\-]+", "-", org_name_clean.lower()).strip("-")

    if not slug:
        raise RegistrationError("Valid organization slug could not be derived.")

    # 3. Check for existing organization by slug or name
    stmt_org = select(Organization).where(
        (Organization.slug == slug) | (Organization.name.ilike(org_name_clean))
    )
    res_org = await session.execute(stmt_org)
    existing_org = res_org.scalars().first()
    if existing_org:
        raise RegistrationError(f"An organization with the name '{org_name_clean}' or slug '{slug}' already exists.")

    # 4. Create new organization
    org = Organization(
        name=org_name_clean,
        slug=slug,
        is_active=True,
    )
    session.add(org)
    await session.flush()

    # 5. Check if user with email already exists in this new org
    email_clean = email.lower().strip()
    stmt_user = select(User).where(
        User.organization_id == org.id,
        User.email == email_clean,
    )
    res_user = await session.execute(stmt_user)
    if res_user.scalars().first():
        raise RegistrationError("An account with this email already exists in this organization.")

    # 6. Create primary Admin user
    admin_user = User(
        organization_id=org.id,
        full_name=full_name.strip(),
        email=email_clean,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    session.add(admin_user)
    await session.commit()
    await session.refresh(admin_user)

    return admin_user


async def request_password_reset(
    session: AsyncSession,
    email: str,
) -> Optional[str]:
    """
    Initiates password reset workflow.
    Does not leak whether the email exists.
    Returns plain token only in development simulation mode.
    """
    email_clean = email.lower().strip()
    stmt = select(User).where(User.email == email_clean)
    res = await session.execute(stmt)
    users = res.scalars().all()

    if not users:
        # Silently succeed to prevent user enumeration
        return None

    # Pick the user (or all matching users across tenants)
    user = users[0]
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )

    reset_record = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        is_used=False,
    )
    session.add(reset_record)
    await session.commit()

    # Development simulation
    if settings.ENABLE_DEV_PASSWORD_RESET_SIMULATION and not settings.is_production:
        DEV_SIMULATED_EMAILS.append({
            "to": email_clean,
            "token": raw_token,
            "expires_at": expires_at.isoformat(),
        })
        logger.info(f"[DEV EMAIL SIMULATION] Password reset token for {email_clean}: {raw_token}")
        return raw_token

    return None


async def reset_password_with_token(
    session: AsyncSession,
    token: str,
    new_password: str,
) -> bool:
    """
    Validates token and updates user password with Argon2id hash.
    Invalidates the single-use token.
    """
    validate_password_policy(new_password)

    token_hash = _hash_token(token.strip())
    stmt = (
        select(PasswordResetToken)
        .options(selectinload(PasswordResetToken.user))
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.is_used.is_(False),
        )
    )
    res = await session.execute(stmt)
    reset_record = res.scalars().first()

    if not reset_record:
        raise ResetPasswordError("Invalid or already used password reset token.")

    if reset_record.is_expired:
        raise ResetPasswordError("Password reset token has expired.")

    user = reset_record.user
    if not user:
        raise ResetPasswordError("Associated user account not found.")

    # Update password and invalidate token
    user.password_hash = hash_password(new_password)
    reset_record.is_used = True
    await session.commit()

    return True
