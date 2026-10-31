from datetime import date
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import SubscriptionPlan, BillingInterval
from app.schemas.plan import PlanCreate, PlanUpdate


class PlanServiceError(Exception):
    """Base exception for plan service errors."""
    pass


class PlanNotFoundError(PlanServiceError):
    """Raised when a requested plan is not found in the tenant organization."""
    pass


class PlanNotAvailableError(PlanServiceError):
    """Raised when attempting to subscribe to a plan outside its availability window."""
    pass


class QuantityBelowMinimumError(PlanServiceError):
    """Raised when requested subscription quantity is below the plan's min_quantity."""
    pass


class PlanService:
    @staticmethod
    async def create_plan(
        session: AsyncSession,
        organization_id: int,
        data: PlanCreate,
    ) -> SubscriptionPlan:
        """
        Creates a new subscription plan with billing frequency and lifecycle policies.
        """
        plan = SubscriptionPlan(
            organization_id=organization_id,
            name=data.name.strip(),
            description=data.description.strip() if data.description else None,
            billing_interval=data.billing_interval,
            interval_count=data.interval_count,
            base_price=data.base_price,
            currency=data.currency.upper(),
            min_quantity=data.min_quantity,
            available_from=data.available_from,
            available_until=data.available_until,
            auto_close_on_expiry=data.auto_close_on_expiry,
            allow_early_close=data.allow_early_close,
            allow_pause=data.allow_pause,
            allow_renewal=data.allow_renewal,
            is_active=data.is_active,
        )
        session.add(plan)
        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    async def get_plan(
        session: AsyncSession,
        organization_id: int,
        plan_id: int,
    ) -> SubscriptionPlan:
        """
        Retrieves a plan by ID scoped strictly to the organization.
        """
        stmt = select(SubscriptionPlan).where(
            and_(
                SubscriptionPlan.id == plan_id,
                SubscriptionPlan.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        plan = result.scalars().first()
        if not plan:
            raise PlanNotFoundError(f"Subscription plan with id {plan_id} not found in this organization.")
        return plan

    @staticmethod
    async def list_plans(
        session: AsyncSession,
        organization_id: int,
        billing_interval: Optional[BillingInterval] = None,
        is_active: Optional[bool] = None,
        available_only: bool = False,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[SubscriptionPlan]:
        """
        Lists plans for an organization with optional filtering by interval, active status, and availability.
        """
        filters = [SubscriptionPlan.organization_id == organization_id]

        if billing_interval is not None:
            filters.append(SubscriptionPlan.billing_interval == billing_interval)

        if is_active is not None:
            filters.append(SubscriptionPlan.is_active == is_active)

        if search:
            search_clean = f"%{search.strip()}%"
            filters.append(SubscriptionPlan.name.ilike(search_clean))

        stmt = (
            select(SubscriptionPlan)
            .where(and_(*filters))
            .order_by(SubscriptionPlan.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        plans = list(result.scalars().all())

        if available_only:
            today = date.today()
            plans = [p for p in plans if p.is_available(today)]

        return plans

    @staticmethod
    async def update_plan(
        session: AsyncSession,
        organization_id: int,
        plan_id: int,
        data: PlanUpdate,
    ) -> SubscriptionPlan:
        """
        Updates plan attributes and lifecycle rules.
        """
        plan = await PlanService.get_plan(session, organization_id=organization_id, plan_id=plan_id)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(plan, key, value)

        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    async def archive_plan(
        session: AsyncSession,
        organization_id: int,
        plan_id: int,
    ) -> SubscriptionPlan:
        """
        Soft-archives a plan to prevent new subscriptions while preserving existing relationships.
        """
        plan = await PlanService.get_plan(session, organization_id=organization_id, plan_id=plan_id)
        plan.is_active = False
        await session.commit()
        await session.refresh(plan)
        return plan

    @staticmethod
    def validate_subscription_eligibility(
        plan: SubscriptionPlan,
        quantity: int,
        target_date: Optional[date] = None,
    ) -> None:
        """
        Validates if a customer or quote can subscribe to this plan:
        1. Plan must be active and within its availability dates.
        2. Requested quantity must satisfy minimum quantity requirements.
        """
        d = target_date or date.today()
        if not plan.is_available(d):
            raise PlanNotAvailableError(
                f"Plan '{plan.name}' is not currently available for new subscriptions on {d}."
            )

        if quantity < plan.min_quantity:
            raise QuantityBelowMinimumError(
                f"Requested quantity {quantity} is below plan '{plan.name}' minimum requirement of {plan.min_quantity}."
            )
