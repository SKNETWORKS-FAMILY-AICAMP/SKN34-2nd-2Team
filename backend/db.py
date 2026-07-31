"""
backend/ 전체가 공유하는 MySQL 커넥션 모듈.
practice-answer/mysql_pipeline/db.py와 같은 패턴(.env 로드 + 커넥션 풀 재사용)을 따르되,
서빙용 DB(kkbox_serving)를 기본값으로 쓴다 — 커리큘럼 실습용 kkbox DB와는 별개.

.env에 아래 항목이 없으면 기본값을 쓴다:
  MYSQL_HOST=127.0.0.1
  MYSQL_PORT=3306
  MYSQL_USER=root
  MYSQL_PASSWORD=1234
  MYSQL_SERVING_DB=kkbox_serving
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent  # backend/ -> 프로젝트 루트
for _p in [_ROOT / ".env", Path(__file__).resolve().parent / ".env"]:
    if _p.exists():
        load_dotenv(_p)
        break
else:
    load_dotenv()


def _config():
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": os.getenv("MYSQL_PORT", "3306"),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "1234"),
        "db": os.getenv("MYSQL_SERVING_DB", "kkbox_serving"),
    }


@lru_cache(maxsize=1)
def get_engine():
    cfg = _config()
    url = f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/{cfg['db']}"
    return create_engine(url, pool_size=5, max_overflow=10, pool_recycle=1800, pool_pre_ping=True)


def get_server_engine():
    """kkbox_serving DB가 아직 없을 때 CREATE DATABASE용 (DB 지정 없이 서버 레벨 접속)."""
    cfg = _config()
    url = f"mysql+pymysql://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}"
    return create_engine(url)
