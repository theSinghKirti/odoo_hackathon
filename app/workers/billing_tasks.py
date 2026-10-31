import asyncio
from datetime import date
from typing import Any, Dict, Optional

from app.db.session import async_session_factory
from app.services.invoice_service import InvoiceService
from app.workers.celery_app import celery_app


async def _execute_billing_sweep(
    as_of_date_iso: Optional[str] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    as_of = date.fromisoformat(as_of_date_iso) if as_of_date_iso else date.today()
    async with async_session_factory() as session:
        invoices = await InvoiceService.run_billing_sweep(
            session=session,
            as_of_date=as_of,
            organization_id=organization_id,
        )
        total_amount = sum(inv.total_amount for inv in invoices)
        return {
            "status": "success",
            "as_of_date": as_of.isoformat(),
            "invoices_generated": len(invoices),
            "total_billed_amount": str(total_amount),
            "invoice_ids": [inv.id for inv in invoices],
        }


@celery_app.task(name="app.workers.billing_tasks.run_daily_billing_sweep")
def run_daily_billing_sweep(
    as_of_date_iso: Optional[str] = None,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Celery task executing automated recurring billing runs.
    Picks up active subscriptions due for billing, creates invoices, and advances cycles.
    """
    return asyncio.run(_execute_billing_sweep(as_of_date_iso=as_of_date_iso, organization_id=organization_id))

