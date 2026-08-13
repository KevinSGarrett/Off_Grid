from fastapi import APIRouter

from app.api.routes.analyst import router as analyst_router
from app.api.routes.commercial import router as commercial_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.crm import router as crm_router
from app.api.routes.exceptions import router as exceptions_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.organizations import router as organizations_router
from app.api.routes.outcomes import router as outcomes_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.projects import router as projects_router

api_router = APIRouter(prefix="/api/v1")
for router in (
    health_router,
    ingest_router,
    projects_router,
    organizations_router,
    outcomes_router,
    contacts_router,
    exceptions_router,
    commercial_router,
    crm_router,
    pipeline_router,
    metrics_router,
    analyst_router,
):
    api_router.include_router(router)
