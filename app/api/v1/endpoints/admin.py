from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.db.session import get_async_db
from app.models.user import User, UserRole
from app.schemas.user import StaffCreate, UserResponse
from app.services.password_service import (
    hash_password,
    validate_password_policy,
    PasswordValidationError,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/users", response_model=List[UserResponse])
async def list_organization_users(
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Admin-only: Retrieve all users within the admin's organization.
    Strict tenant isolation enforced by current_admin.organization_id.
    """
    stmt = (
        select(User)
        .where(User.organization_id == current_admin.organization_id)
        .order_by(User.id)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_staff_user(
    payload: StaffCreate,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Admin-only: Provision a new Staff account within the admin's organization.
    """
    try:
        validate_password_policy(payload.password)
    except PasswordValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # Verify email uniqueness in tenant
    stmt = select(User).where(
        User.organization_id == current_admin.organization_id,
        User.email == payload.email.lower().strip(),
    )
    res = await db.execute(stmt)
    if res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists in your organization.",
        )

    staff_user = User(
        organization_id=current_admin.organization_id,
        full_name=payload.full_name.strip(),
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.STAFF,
        is_active=True,
        is_verified=True,
    )
    db.add(staff_user)
    await db.commit()
    await db.refresh(staff_user)
    return staff_user

