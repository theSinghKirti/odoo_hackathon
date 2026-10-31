from datetime import date
from typing import List, Optional, Union
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.plan import BillingInterval
from app.models.subscription import Subscription, SubscriptionLine, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.quotation_service import advance_date


class SubscriptionServiceError(Exception):
    """Base exception for subscription errors."""
    pass


class SubscriptionNotFoundError(SubscriptionServiceError):
    pass


class InvalidSubscriptionStateError(SubscriptionServiceError):
    pass


class SubscriptionPolicyViolationError(SubscriptionServiceError):
    pass


class SubscriptionAccessDeniedError(SubscriptionServiceError):
    pass


class SubscriptionService:
    @staticmethod
    async def get_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        user: Optional[User] = None,
    ) -> Subscription:
        """
        Retrieves a subscription with lines, customer, and plan relationships loaded.
        Enforces tenant isolation and customer portal ownership check.
        """
        stmt = (
            select(Subscription)
            .options(
                selectinload(Subscription.lines).selectinload(SubscriptionLine.product),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.variant),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.tax_rule),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.discount_rule),
                selectinload(Subscription.customer),
                selectinload(Subscription.plan),
                selectinload(Subscription.quotation),
            )
            .where(
                and_(
                    Subscription.id == subscription_id,
                    Subscription.organization_id == organization_id,
                )
            )
        )
        res = await session.execute(stmt)
        sub = res.scalars().first()
        if not sub:
            raise SubscriptionNotFoundError(f"Subscription {subscription_id} not found in this organization.")

        # Customer portal access control
        if user and user.role == UserRole.CUSTOMER:
            if sub.customer and sub.customer.user_id != user.id and sub.customer.email.lower() != user.email.lower():
                raise SubscriptionAccessDeniedError("Access to this subscription is restricted to its owner.")

        return sub

    @staticmethod
    async def list_subscriptions(
        session: AsyncSession,
        organization_id: int,
        status: Optional[Union[SubscriptionStatus, str]] = None,
        customer_id: Optional[int] = None,
        user: Optional[User] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Subscription]:
        """
        Lists subscriptions scoped to tenant organization.
        Supports filtering by status, customer, and search query.
        For customer role, automatically restricts to subscriptions owned by that customer.
        """
        filters = [Subscription.organization_id == organization_id]

        if user and user.role == UserRole.CUSTOMER:
            # Find customer ID for this user
            c_stmt = select(Customer.id).where(
                and_(
                    Customer.organization_id == organization_id,
                    (Customer.user_id == user.id) | (Customer.email == user.email),
                )
            )
            c_res = await session.execute(c_stmt)
            owned_ids = c_res.scalars().all()
            if not owned_ids:
                return []
            filters.append(Subscription.customer_id.in_(owned_ids))
        elif customer_id is not None:
            filters.append(Subscription.customer_id == customer_id)

        if status is not None and status != "all":
            if isinstance(status, str):
                try:
                    st_enum = SubscriptionStatus(status.lower())
                    filters.append(Subscription.status == st_enum)
                except ValueError:
                    pass
            else:
                filters.append(Subscription.status == status)

        stmt = (
            select(Subscription)
            .options(
                selectinload(Subscription.lines).selectinload(SubscriptionLine.product),
                selectinload(Subscription.lines).selectinload(SubscriptionLine.variant),
                selectinload(Subscription.customer),
                selectinload(Subscription.plan),
            )
            .where(and_(*filters))
            .order_by(Subscription.id.desc())
        )

        if search:
            s_clean = f"%{search.strip().lower()}%"
            stmt = stmt.outerjoin(Customer, Subscription.customer_id == Customer.id).where(
                or_(
                    func.lower(Subscription.subscription_number).like(s_clean),
                    func.lower(Customer.name).like(s_clean),
                )
            )

        stmt = stmt.offset(skip).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def pause_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        user: Optional[User] = None,
    ) -> Subscription:
        """
        Pauses an active subscription if plan policy allows (allow_pause = True).
        Suspends automated recurring billing until resumed.
        """
        sub = await SubscriptionService.get_subscription(session, organization_id, subscription_id, user=user)

        if sub.status != SubscriptionStatus.ACTIVE:
            raise InvalidSubscriptionStateError(f"Cannot pause subscription with status '{sub.status}'. Only Active subscriptions can be paused.")

        if not sub.allow_pause:
            raise SubscriptionPolicyViolationError(f"Subscription {sub.subscription_number} plan policy does not permit pausing.")

        sub.status = SubscriptionStatus.PAUSED
        await session.commit()
        return await SubscriptionService.get_subscription(session, organization_id, sub.id)

    @staticmethod
    async def resume_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        user: Optional[User] = None,
    ) -> Subscription:
        """
        Resumes a paused subscription back to ACTIVE.
        Recalculates next_billing_date if the previous billing date passed while on pause.
        """
        sub = await SubscriptionService.get_subscription(session, organization_id, subscription_id, user=user)

        if sub.status != SubscriptionStatus.PAUSED:
            raise InvalidSubscriptionStateError(f"Cannot resume subscription with status '{sub.status}'. Only Paused subscriptions can be resumed.")

        today = date.today()
        if sub.next_billing_date <= today and sub.plan:
            # Recalculate next billing date from today
            sub.next_billing_date = advance_date(today, sub.plan.billing_interval, sub.plan.interval_count)

        sub.status = SubscriptionStatus.ACTIVE
        await session.commit()
        return await SubscriptionService.get_subscription(session, organization_id, sub.id)

    @staticmethod
    async def close_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        user: Optional[User] = None,
        reason: Optional[str] = None,
    ) -> Subscription:
        """
        Closes a subscription. Terminal state.
        If closing early before expiry_date, enforces allow_early_close policy toggle.
        """
        sub = await SubscriptionService.get_subscription(session, organization_id, subscription_id, user=user)

        if sub.status == SubscriptionStatus.CLOSED:
            raise InvalidSubscriptionStateError(f"Subscription {sub.subscription_number} is already closed.")

        today = date.today()
        # Early close check
        if today < sub.expiry_date and not sub.allow_early_close:
            raise SubscriptionPolicyViolationError(
                f"Subscription {sub.subscription_number} contract prohibits early termination before {sub.expiry_date}."
            )

        sub.status = SubscriptionStatus.CLOSED
        if reason:
            existing_notes = f"{sub.notes}\n" if sub.notes else ""
            sub.notes = f"{existing_notes}[Closed on {today}]: {reason}".strip()

        await session.commit()
        return await SubscriptionService.get_subscription(session, organization_id, sub.id)

    @staticmethod
    async def renew_subscription(
        session: AsyncSession,
        organization_id: int,
        subscription_id: int,
        user: Optional[User] = None,
    ) -> Subscription:
        """
        Renews a subscription if plan policy allows (allow_renewal = True).
        Extends expiry_date and reactivates subscription.
        """
        sub = await SubscriptionService.get_subscription(session, organization_id, subscription_id, user=user)

        if not sub.allow_renewal:
            raise SubscriptionPolicyViolationError(f"Subscription {sub.subscription_number} plan policy prohibits renewals.")

        today = date.today()
        plan = sub.plan
        interval = plan.billing_interval if plan else BillingInterval.MONTHLY
        interval_count = plan.interval_count if plan else 1

        # Advance expiry by 1 billing cycle
        base_expiry = sub.expiry_date if sub.expiry_date > today else today
        new_expiry = advance_date(base_expiry, interval, interval_count)

        sub.expiry_date = new_expiry
        if sub.status == SubscriptionStatus.CLOSED or sub.next_billing_date <= today:
            sub.next_billing_date = advance_date(today, interval, interval_count)

        sub.status = SubscriptionStatus.ACTIVE
        await session.commit()
        return await SubscriptionService.get_subscription(session, organization_id, sub.id)
