import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import router
from app.chat import router as chat_router
from app.db import engine
from app.skills import router as skills_router
from app.trace import TraceMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# httpx logs full URLs by default; webhook URLs contain credentials.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="Webhook 中转站",
    version="1.0.0",
    lifespan=lifespan,
    description="Gitee / 夜莺 / 通用回调 → LLM → 飞书 / 企业微信 / 钉钉。管理接口使用 Bearer JWT。",
)
app.add_middleware(TraceMiddleware)
app.include_router(router)
app.include_router(skills_router)
app.include_router(chat_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # FastAPI's default input field can accidentally echo plaintext credentials.
    details = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": details})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "unknown")
    logging.getLogger("station").error(
        "unhandled trace_id=%s error_type=%s", trace_id, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务暂时不可用", "trace_id": trace_id},
        headers={"X-Trace-Id": trace_id},
    )
