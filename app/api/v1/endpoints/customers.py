from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_staff_or_admin
from app.db.session import get_async_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerResponse

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=List[CustomerResponse])
async def list_customers(
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Staff & Admin: List all customers belonging to the current user's organization.
    """
    stmt = (
        select(Customer)
        .where(Customer.organization_id == current_user.organization_id)
        .order_by(Customer.id)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Staff & Admin: Retrieve a customer by ID.
    Enforces strict tenant isolation: rejects cross-tenant lookups even if customer_id exists in another tenant.
    """
    stmt = select(Customer).where(
        Customer.id == customer_id,
        Customer.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    customer = result.scalars().first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found in your organization.",
        )
    return customer


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Staff & Admin: Create a new customer record under the current user's organization.
    """
    # Enforce email uniqueness in tenant
    stmt = select(Customer).where(
        Customer.organization_id == current_user.organization_id,
        Customer.email == payload.email.lower().strip(),
    )
    res = await db.execute(stmt)
    if res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A customer with this email already exists in your organization.",
        )

    customer = Customer(
        organization_id=current_user.organization_id,
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        phone=payload.phone.strip() if payload.phone else None,
        address=payload.address.strip() if payload.address else None,
        is_active=True,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer

