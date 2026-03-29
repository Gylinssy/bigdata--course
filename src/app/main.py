from __future__ import annotations

from time import perf_counter

from core.env_utils import load_env_file
from core.runtime_log import RuntimeLogger, new_run_id
from fastapi import FastAPI
from fastapi import Request

load_env_file()

from .api import router


app = FastAPI(title="startup-edu-agent", version="0.1.0")
app.include_router(router)
runtime_logger = RuntimeLogger()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    run_id = new_run_id("http")
    started_at = perf_counter()
    runtime_logger.log(
        "api",
        "request_started",
        run_id=run_id,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        runtime_logger.log_exception(
            "api",
            "request_failed",
            run_id=run_id,
            error=exc,
            method=request.method,
            path=request.url.path,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise

    runtime_logger.log(
        "api",
        "request_completed",
        run_id=run_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return response
