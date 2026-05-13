"""Vercel entrypoint for the FastAPI application."""

from api.office import router as office_router
from web.app import app

app.include_router(office_router)
