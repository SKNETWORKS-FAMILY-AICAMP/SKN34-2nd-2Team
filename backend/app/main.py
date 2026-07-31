"""
FastAPI 진입점.

실행 (backend/ 폴더에서):
    uvicorn app.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs  (모든 엔드포인트 여기서 바로 테스트 가능)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin_router, auth_router, me_router

app = FastAPI(title="KKBOX Churn Serving API")

# React 개발 서버 기본 포트(Vite=5173, CRA=3000) 둘 다 허용해둠 — 실제 배포 시 좁혀주세요.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
