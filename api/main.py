from api import bootstrap as bootstrap

from fastapi import FastAPI

from api.database import SessionLocal, init_db
from api.errors import register_exception_handlers
from api.routes import router
from api.voices import sync_voice_directory


def create_app() -> FastAPI:
    app = FastAPI(title="VoxCPM OpenAI-Compatible API", version="0.1.0")
    register_exception_handlers(app)
    app.include_router(router)

    @app.on_event("startup")
    def startup() -> None:
        init_db()
        with SessionLocal() as db:
            sync_voice_directory(db)

    return app


app = create_app()
