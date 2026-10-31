from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax import TaxRule
from app.schemas.tax import TaxRuleCreate, TaxRuleUpdate


class TaxServiceError(Exception):
    """Base exception for tax service errors."""
    pass


class TaxRuleNotFoundError(TaxServiceError):
    """Raised when a requested tax rule is not found in the tenant organization."""
    pass


class TaxService:
    @staticmethod
    async def create_tax_rule(
        session: AsyncSession,
        organization_id: int,
        data: TaxRuleCreate,
    ) -> TaxRule:
        """
        Creates an organization-specific tax rule (e.g. GST 18%).
        """
        tax_rule = TaxRule(
            organization_id=organization_id,
            name=data.name.strip(),
            rate=data.rate,
            is_active=data.is_active,
        )
        session.add(tax_rule)
        await session.commit()
        await session.refresh(tax_rule)
        return tax_rule

    @staticmethod
    async def get_tax_rule(
        session: AsyncSession,
        organization_id: int,
        tax_rule_id: int,
    ) -> TaxRule:
        """
        Retrieves a tax rule by ID scoped strictly to the organization.
        """
        stmt = select(TaxRule).where(
            and_(
                TaxRule.id == tax_rule_id,
                TaxRule.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        rule = result.scalars().first()
        if not rule:
            raise TaxRuleNotFoundError(f"Tax rule with id {tax_rule_id} not found in this organization.")
        return rule

    @staticmethod
    async def list_tax_rules(
        session: AsyncSession,
        organization_id: int,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[TaxRule]:
        """
        Lists tax rules configured for the organization.
        """
        filters = [TaxRule.organization_id == organization_id]
        if is_active is not None:
            filters.append(TaxRule.is_active == is_active)

        stmt = (
            select(TaxRule)
            .where(and_(*filters))
            .order_by(TaxRule.id.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_tax_rule(
        session: AsyncSession,
        organization_id: int,
        tax_rule_id: int,
        data: TaxRuleUpdate,
    ) -> TaxRule:
        """
        Updates an existing tax rule's name, rate, or active status.
        """
        rule = await TaxService.get_tax_rule(session, organization_id=organization_id, tax_rule_id=tax_rule_id)

        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(rule, key, value)

        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    async def archive_tax_rule(
        session: AsyncSession,
        organization_id: int,
        tax_rule_id: int,
    ) -> TaxRule:
        """
        Soft-archives a tax rule to preserve historical references on issued invoices.
        """
        rule = await TaxService.get_tax_rule(session, organization_id=organization_id, tax_rule_id=tax_rule_id)
        rule.is_active = False
        await session.commit()
        await session.refresh(rule)
        return rule

    @staticmethod
    def compute_tax(amount: Decimal, rate: Decimal) -> Decimal:
        """
        Computes tax on an amount using exact decimal arithmetic.
        """
        if amount <= Decimal("0.00") or rate <= Decimal("0.00"):
            return Decimal("0.00")
        tax = amount * (rate / Decimal("100.00"))
        return round(tax, 2)
