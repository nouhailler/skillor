from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import router
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.services.seed import seed_database
from app.services.search import ensure_search_index

@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema: Base.metadata.create_all(bind=engine)
    if settings.seed_on_start:
        with SessionLocal() as db: seed_database(db)
    with SessionLocal() as db:
        ensure_search_index(db)
    yield

app=FastAPI(title="Skillor API",version="1.0.0",description="API de connaissance du marché des compétences",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["GET","POST"],allow_headers=["*"])
app.include_router(router)

@app.get("/")
def root(): return {"name":"Skillor API","docs":"/docs","health":"/api/v1/health"}
