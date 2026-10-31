from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_organization, require_admin, require_staff_or_admin
from app.db.session import get_async_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.quotation_template import (
    QuotationTemplateCreate,
    QuotationTemplateResponse,
    QuotationTemplateUpdate,
)
from app.services.quotation_service import (
    QuotationTemplateNotFoundError,
    QuotationTemplateService,
)

router = APIRouter(prefix="/quotation-templates", tags=["Quotation Templates"])


@router.get("", response_model=List[QuotationTemplateResponse])
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """List standard quotation templates for this organization."""
    return await QuotationTemplateService.list_templates(
        session=db,
        organization_id=current_org.id,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=QuotationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: QuotationTemplateCreate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a new standardized quotation package template."""
    return await QuotationTemplateService.create_template(
        session=db,
        organization_id=current_org.id,
        data=data,
    )


@router.get("/{template_id}", response_model=QuotationTemplateResponse)
async def get_template(
    template_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve details of a quotation template."""
    try:
        return await QuotationTemplateService.get_template(
            session=db,
            organization_id=current_org.id,
            template_id=template_id,
        )
    except QuotationTemplateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{template_id}", response_model=QuotationTemplateResponse)
async def update_template(
    template_id: int,
    data: QuotationTemplateUpdate,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_staff_or_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Update a quotation template."""
    try:
        return await QuotationTemplateService.update_template(
            session=db,
            organization_id=current_org.id,
            template_id=template_id,
            data=data,
        )
    except QuotationTemplateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    current_org: Organization = Depends(get_current_organization),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a quotation template (restricted to Admin)."""
    try:
        await QuotationTemplateService.delete_template(
            session=db,
            organization_id=current_org.id,
            template_id=template_id,
        )
    except QuotationTemplateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
