"""
FastAPI application with PostGIS backend.
Handles application lifecycle (startup/shutdown) and route registration.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database_manager import get_db_connection_pool, initialize_schema
from app.exception_handlers import EXCEPTION_HANDLERS
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.
    Runs on startup (before yield) and shutdown (after yield).
    """
    # Startup: initialize and connect backend
    connection_pool = get_db_connection_pool(settings.connection_url)
    await connection_pool.open()
    async with connection_pool.connection() as conn:
        await initialize_schema(conn)
    print("✓ Connected to PostGIS")

    yield {"connection_pool": connection_pool}

    # Shutdown: disconnect backend
    await connection_pool.close()
    print("✓ Disconnected from PostGIS")


# Create FastAPI application
app = FastAPI(
    title="Opplæring api",
    description="REST API for storing and querying FKB Bane",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.APP_ENV == "development",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_headers=["*"], allow_methods=["*"]
)

app.include_router(router)

for exc_class, exc_handler in EXCEPTION_HANDLERS.items():
    app.add_exception_handler(exc_class, exc_handler)
