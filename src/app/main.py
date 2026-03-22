from __future__ import annotations

from core.env_utils import load_env_file
from fastapi import FastAPI

load_env_file()

from .api import router


app = FastAPI(title="startup-edu-agent", version="0.1.0")
app.include_router(router)
