"""
FastAPI 진입점.

실행 (backend/ 폴더에서):
    uvicorn app.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs  (모든 엔드포인트 여기서 바로 테스트 가능)
프론트 페이지: http://localhost:8000/ (고객), http://localhost:8000/admin-page (관리자)
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routers import admin_router, auth_router, me_router

app = FastAPI(title="KKBOX Churn Serving API")

# backend/app/main.py -> 프로젝트 루트 -> frontend/
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

# React 개발 서버 기본 포트(Vite=5173, CRA=3000)와, HTML 파일을 file://로 직접 열 때
# 브라우저가 보내는 origin("null")까지 허용해둠 — 실제 배포 시 좁혀주세요.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(me_router.router, prefix="/me", tags=["me"])
app.include_router(admin_router.router, prefix="/admin", tags=["admin"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def customer_page():
    """고객 사이트 — http://localhost:8000/ 로 바로 접속."""
    return FileResponse(FRONTEND_DIR / "kkbox_customer.html")


@app.get("/admin-page")
def admin_page():
    """관리자 사이트 — http://localhost:8000/admin-page 로 바로 접속.
    ('/admin'은 이미 admin_router의 API prefix라 경로를 다르게 잡음)"""
    return FileResponse(FRONTEND_DIR / "kkbox_admin.html")
