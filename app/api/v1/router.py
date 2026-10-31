from fastapi import APIRouter
from app.api.v1.endpoints import (
    admin,
    analytics,
    auth,
    customers,
    discounts,
    health,
    invoices,
    payments,
    plans,
    products,
    quotations,
    quotation_templates,
    subscriptions,
    taxes,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(customers.router)
api_router.include_router(products.router)
api_router.include_router(plans.router)
api_router.include_router(taxes.router)
api_router.include_router(discounts.router)
api_router.include_router(quotation_templates.router)
api_router.include_router(quotations.router)
api_router.include_router(subscriptions.router)
api_router.include_router(invoices.router)
api_router.include_router(payments.router)
api_router.include_router(analytics.router)
api_router.include_router(health.router)
