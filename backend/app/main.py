from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import auth_router
from app.config import get_settings
from app.errors import register_error_handlers
from app.storage import storage_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    if get_settings().database_url:
        from app.db.session import close_engine
        await close_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(storage_router)
    app.include_router(storage_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["Health"])
    @app.get(f"{settings.api_prefix}/health", tags=["Health"])
    async def health_check() -> dict:
        result: dict = {"status": "healthy", "environment": settings.environment, "app": settings.app_name}
        if settings.database_url:
            from app.db.health import check_db_connectivity
            db_result = await check_db_connectivity()
            result["database"] = {"status": db_result.status, "message": db_result.message}
            if db_result.status == "error":
                result["status"] = "degraded"
        else:
            result["database"] = {"status": "unconfigured"}
        return result

    return app


app = create_app()
