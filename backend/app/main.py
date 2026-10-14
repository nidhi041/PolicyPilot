from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    @app.get("/health", tags=["Health"])
    @app.get(f"{settings.api_prefix}/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "environment": settings.environment,
            "app": settings.app_name,
        }

    return app


app = create_app()
