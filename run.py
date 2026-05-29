#!/usr/bin/env python3
"""Запуск веб-интерфейса AI Office."""

import os
import sys

sys.path.insert(0, '.')

import uvicorn

from api.office import router as office_router
from web.app import app

app.include_router(office_router)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        log_level="info",
    )
