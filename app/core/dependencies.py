from typing import Callable, List, Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.user import User, UserRole


def extract_token_from_request(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """
    Extracts JWT from:
    1. HTTP-Only Cookie ('access_token')
    2. Authorization Header ('Bearer <token>')
    """
    # 1. Check HTTP-only cookie first
    cookie_token = request.cookies.get(settings.COOKIE_NAME)
    if cookie_token:
        return cookie_token

    # 2. Check Authorization header
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    authorization: Optional[str] = Header(None),
) -> User:
    """
    Resolves the current authenticated user from JWT.
    Enforces active user check and active tenant check.
    """
    token = extract_token_from_request(request, authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token payload.",
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed user ID in token.",
        )

    stmt = (
        select(User)
        .options(selectinload(User.organization))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or credentials revoked.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    if not user.organization or not user.organization.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant organization is deactivated.",
        )

    return user


async def get_current_organization(
    current_user: User = Depends(get_current_user),
) -> Organization:
    """
    Returns the verified active Organization of the authenticated user.
    Server-side authoritative tenant context.
    """
    return current_user.organization


def require_roles(*allowed_roles: UserRole) -> Callable:
    """
    RBAC dependency factory.
    Enforces that current_user has one of the allowed roles.
    """
    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Access requires one of roles {[r.value for r in allowed_roles]}.",
            )
        return current_user

    return role_checker


# Convenient RBAC dependencies
require_admin = require_roles(UserRole.ADMIN)
require_staff_or_admin = require_roles(UserRole.ADMIN, UserRole.STAFF)
require_customer = require_roles(UserRole.CUSTOMER)

