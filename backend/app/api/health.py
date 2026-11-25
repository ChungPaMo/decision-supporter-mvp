from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine

router = APIRouter()


class DatabaseHealthy(BaseModel):
    status: Literal["ok"]
    server_version: str


class DatabaseUnavailable(BaseModel):
    status: Literal["unavailable"]


class HealthOk(BaseModel):
    status: Literal["ok"]
    version: str
    database: DatabaseHealthy


class HealthDegraded(BaseModel):
    status: Literal["degraded"]
    version: str
    database: DatabaseUnavailable


@router.get("/health", response_model=HealthOk, summary="서버·DB 상태 확인", responses={
    503: {"model": HealthDegraded, "description": "서버에 연결됐으나 데이터베이스를 사용할 수 없음"},
})
def health() -> JSONResponse:
    """DB 연결이 되면 200, 안 되면 503. DB 오류 상세(접속 정보 포함 가능)는 응답에 싣지 않는다."""
    body = {"status": "ok", "version": get_settings().app_version, "database": {"status": "ok"}}
    try:
        with get_engine().connect() as conn:
            body["database"]["server_version"] = conn.execute(text("SHOW server_version")).scalar_one()
    except Exception:
        body["status"] = "degraded"
        body["database"] = {"status": "unavailable"}
        return JSONResponse(body, status_code=503)
    return JSONResponse(body)
