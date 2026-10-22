from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.analytics import analytics_router
from app.auth import auth_router
from app.config import get_settings
from app.errors import register_error_handlers
from app.chat import chat_router, conversations_router
from app.policies import policies_router
from app.search import search_router
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
    app.include_router(policies_router)
    app.include_router(policies_router, prefix=settings.api_prefix)
    app.include_router(search_router)
    app.include_router(search_router, prefix=settings.api_prefix)
    app.include_router(chat_router)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(conversations_router)
    app.include_router(conversations_router, prefix=settings.api_prefix)
    app.include_router(analytics_router)
    app.include_router(analytics_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["Health"])
    @app.get(f"{settings.api_prefix}/health", tags=["Health"])
    async def health_check(response: Response) -> dict:
        result: dict = {"status": "healthy", "environment": settings.environment, "app": settings.app_name}
        if settings.database_url:
            from app.db.health import check_db_connectivity
            db_result = await check_db_connectivity()
            result["database"] = {"status": db_result.status, "message": db_result.message}
            if db_result.status == "error":
                result["status"] = "degraded"
                response.status_code = 503
        else:
            result["database"] = {"status": "unconfigured"}
        return result

    return app


app = create_app()
