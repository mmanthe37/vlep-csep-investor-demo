"""VLEP Pipeline — API Routers Package."""
from vlep.api.routers.csep import router as csep_router
from vlep.api.routers.evidence import router as evidence_router
from vlep.api.routers.governance import router as governance_router
from vlep.api.routers.literature import router as literature_router
from vlep.api.routers.patients import router as patients_router
from vlep.api.routers.phenotypes import router as phenotypes_router

__all__ = [
    "patients_router",
    "evidence_router",
    "literature_router",
    "phenotypes_router",
    "csep_router",
    "governance_router",
]
