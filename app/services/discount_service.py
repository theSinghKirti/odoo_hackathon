from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discount import DiscountRule, DiscountScope, DiscountType
from app.schemas.discount import DiscountRuleCreate, DiscountRuleUpdate


class DiscountServiceError(Exception):
    """Base exception for discount service errors."""
    pass


class DiscountRuleNotFoundError(DiscountServiceError):
    """Raised when a requested discount rule is not found in the tenant organization."""
    pass


class DiscountService:
    @staticmethod
    async def create_discount_rule(
        session: AsyncSession,
        organization_id: int,
        data: DiscountRuleCreate,
    ) -> DiscountRule:
        """
        Creates an Admin discount rule: fixed amount or percentage, with minimum spend/quantity,
        start/end dates, max uses, and product vs subscription scope.
        """
        rule = DiscountRule(
            organization_id=organization_id,
            name=data.name.strip(),
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            min_purchase_amount=data.min_purchase_amount,
            min_quantity=data.min_quantity,
            start_date=data.start_date,
            end_date=data.end_date,
            max_uses=data.max_uses,
            scope=data.scope,
            product_id=data.product_id if data.scope == DiscountScope.PRODUCT else None,
            is_active=data.is_active,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def get_discount_rule(
        session: AsyncSession,
        organization_id: int,
        rule_id: int,
    ) -> DiscountRule:
        """
        Retrieves a discount rule by ID scoped strictly to the organization.
        """
        stmt = (
            select(DiscountRule)
            .options(selectinload(DiscountRule.product))
            .where(
                and_(
                    DiscountRule.id == rule_id,
                    DiscountRule.organization_id == organization_id,
                )
            )
        )
        result = await session.execute(stmt)
        rule = result.scalars().first()
        if not rule:
            raise DiscountRuleNotFoundError(f"Discount rule with id {rule_id} not found in this organization.")
        return rule

    @staticmethod
    async def list_discount_rules(
        session: AsyncSession,
        organization_id: int,
        scope: Optional[DiscountScope] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[DiscountRule]:
        """
        Lists discount rules for an organization with optional scope and active filtering.
        """
        filters = [DiscountRule.organization_id == organization_id]
        if scope is not None:
            filters.append(DiscountRule.scope == scope)
        if is_active is not None:
            filters.append(DiscountRule.is_active == is_active)

        stmt = (
            select(DiscountRule)
            .options(selectinload(DiscountRule.product))
            .where(and_(*filters))
            .order_by(DiscountRule.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_discount_rule(
        session: AsyncSession,
        organization_id: int,
        rule_id: int,
        data: DiscountRuleUpdate,
    ) -> DiscountRule:
        """
        Updates an existing discount rule.
        """
        rule = await DiscountService.get_discount_rule(session, organization_id=organization_id, rule_id=rule_id)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(rule, key, value)

        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def archive_discount_rule(
        session: AsyncSession,
        organization_id: int,
        rule_id: int,
    ) -> DiscountRule:
        """
        Soft-archives a discount rule so it no longer triggers on new billing operations.
        """
        rule = await DiscountService.get_discount_rule(session, organization_id=organization_id, rule_id=rule_id)
        rule.is_active = False
        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def evaluate_and_apply_discount(
        session: AsyncSession,
        organization_id: int,
        rule_id: int,
        base_amount: Decimal,
        quantity: int = 1,
        target_date: Optional[date] = None,
        target_product_id: Optional[int] = None,
        record_usage: bool = False,
    ) -> Tuple[bool, Decimal]:
        """
        Evaluates qualification criteria for a discount rule.
        If eligible, calculates discount and optionally records usage (increments times_used).
        Returns: (is_applied, discount_amount)
        """
        rule = await DiscountService.get_discount_rule(session, organization_id=organization_id, rule_id=rule_id)

        if not rule.is_eligible(
            amount=base_amount,
            quantity=quantity,
            target_date=target_date,
            target_product_id=target_product_id,
        ):
            return False, Decimal("0.00")

        discount_amount = rule.calculate_discount(base_amount)

        if record_usage and discount_amount > Decimal("0.00"):
            rule.times_used += 1
            await session.commit()
            await session.refresh(rule)

        return True, discount_amount
