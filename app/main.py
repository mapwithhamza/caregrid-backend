import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_DESCRIPTION, APP_NAME, APP_VERSION
from app.data_loader import data_store
from app.routers import agent, facilities, impact, search, stats


logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def load_data_on_startup() -> None:
    try:
        data_store.validate_all()
        logger.info("CareGrid CSV data loaded and validated successfully.")
    except FileNotFoundError as exc:
        data_store.last_error = str(exc)
        logger.warning("CareGrid CSV data not loaded: %s", exc)
    except ValueError as exc:
        data_store.last_error = str(exc)
        logger.warning("CareGrid CSV validation failed: %s", exc)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "CareGrid India API scaffold ready"}


@app.get("/health")
def health_check() -> dict[str, Any]:
    data_loaded = data_store.is_validated
    response: dict[str, Any] = {
        "status": "healthy" if data_loaded else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "data_loaded": data_loaded,
        "endpoints_ready": True,
        "tests_expected": "python -m pytest",
    }

    if data_store.validation_summary:
        response["facility_rows"] = data_store.validation_summary["facility_rows"]

    return response


app.include_router(facilities.router, prefix="/facilities", tags=["facilities"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(impact.router, prefix="/impact", tags=["impact"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])
