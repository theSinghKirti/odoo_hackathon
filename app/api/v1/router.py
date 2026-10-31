from fastapi import APIRouter
from app.api.v1.endpoints import auth, admin, customers, health, products, plans

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(customers.router)
api_router.include_router(products.router)
api_router.include_router(plans.router)
api_router.include_router(health.router)

