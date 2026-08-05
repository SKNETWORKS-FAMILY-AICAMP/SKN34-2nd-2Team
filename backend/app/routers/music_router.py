"""GET /music/* — Apple Music(iTunes) 공개 API 프록시.

브라우저(kkbox_customer.html)가 itunes.apple.com / rss.marketingtools.apple.com을
직접 fetch()하면 사용자 네트워크 환경에 따라 CORS나 방화벽 정책으로 막힐 수 있다.
그래서 백엔드가 대신 호출해서 결과만 그대로(또는 가공해서) 돌려준다 — 브라우저는
항상 같은 오리진(localhost:8000)만 호출하므로 CORS 문제 자체가 생기지 않는다.

우리 DB와 무관한 공개 음원 메타데이터라 로그인 여부와 상관없이 열어둔다(require_staff/
require_customer 의존성 없음).
"""
import time

import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
APPLE_CHART_URL = "https://rss.marketingtools.apple.com/api/v2/kr/music/most-played"

TIMEOUT = 6  # seconds — 발표 중 API가 느려도 화면이 무한정 멈추지 않게

# ---------------------------------------------------------------------------
# 서버 메모리 캐시 — 발표 당일 Apple 쪽 레이트리밋/일시 장애가 나도 화면이
# 안 죽게 하는 안전장치. 프로세스 메모리에만 두는 단순 dict라 재시작하면
# 비워지지만, 이 데모 목적에는 그걸로 충분하다(별도 Redis 등 불필요).
# ---------------------------------------------------------------------------
_CACHE = {}  # key -> (expires_at_epoch_seconds, value)
CHART_TTL = 60 * 20         # 차트: 20분 (거의 안 바뀌는 데이터라 넉넉히)
SEARCH_TTL = 60 * 60 * 6    # 검색: 6시간 (컴백/로열 추천 쿼리가 고정 문자열이라 길게 둬도 무방)
NEW_RELEASES_TTL = 60 * 20  # 최신음악: 차트와 같은 소스라 20분


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if time.time() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value, ttl: int):
    _CACHE[key] = (time.time() + ttl, value)


@router.get("/search")
def search_track(term: str = Query(..., min_length=1), limit: int = Query(1, ge=1, le=200)):
    """iTunes Search API 그대로 프록시 (응답 형태 동일: {resultCount, results: [...]}).
    같은 term+limit 조합은 SEARCH_TTL 동안 캐시해서 재호출 시 Apple API를 다시 안 부른다."""
    cache_key = f"search:{term}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        res = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": term, "country": "KR", "media": "music", "limit": limit},
            timeout=TIMEOUT,
        )
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"iTunes 검색 실패: {e}")
    _cache_set(cache_key, data, SEARCH_TTL)
    return data


@router.get("/chart")
def top_chart(limit: int = Query(100, ge=1, le=200)):
    """Apple Music 공식 대한민국 차트 + iTunes lookup으로 30초 미리듣기 URL 보강해서
    [{rank, title, artist, artwork, previewUrl}, ...] 형태로 반환. CHART_TTL 동안 캐시."""
    cache_key = f"chart:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        res = requests.get(f"{APPLE_CHART_URL}/{limit}/songs.json", timeout=TIMEOUT)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"차트 조회 실패: {e}")

    entries = ((data.get("feed") or {}).get("results")) or []
    if not entries:
        raise HTTPException(status_code=502, detail="차트 데이터가 비어있습니다")

    ids = [str(e["id"]) for e in entries if e.get("id")]
    preview_map = {}
    if ids:
        try:
            lookup_res = requests.get(
                ITUNES_LOOKUP_URL, params={"id": ",".join(ids), "country": "KR"}, timeout=TIMEOUT
            )
            if lookup_res.ok:
                for r in lookup_res.json().get("results", []):
                    if r.get("trackId"):
                        preview_map[str(r["trackId"])] = r.get("previewUrl")
        except requests.RequestException:
            pass  # 미리듣기 보강만 실패한 것 — 차트 자체는 그대로 반환

    result = [
        {
            "rank": i + 1,
            "title": e.get("name"),
            "artist": e.get("artistName"),
            "artwork": e.get("artworkUrl100"),
            "previewUrl": preview_map.get(str(e.get("id"))),
        }
        for i, e in enumerate(entries)
    ]
    _cache_set(cache_key, result, CHART_TTL)
    return result


@router.get("/new-releases")
def new_releases(limit: int = Query(24, ge=1, le=200)):
    """대한민국 Apple Music 인기 차트(최대 200곡) 중에서 실제 발매일(releaseDate)이
    가장 최근인 곡들만 골라 반환한다. Apple 공개 API에는 별도의 "신곡" 전용 차트가
    없어서(테스트 결과 /music/new-releases 형태의 피드는 404), 기존 인기 차트 피드를
    그대로 재사용하되 정렬 기준만 인기순 → 발매일순으로 바꾼다. NEW_RELEASES_TTL 동안 캐시."""
    cache_key = f"new-releases:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        res = requests.get(f"{APPLE_CHART_URL}/200/songs.json", timeout=TIMEOUT)
        res.raise_for_status()
        data = res.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"최신음악 조회 실패: {e}")

    entries = ((data.get("feed") or {}).get("results")) or []
    if not entries:
        raise HTTPException(status_code=502, detail="최신음악 데이터가 비어있습니다")

    entries = [e for e in entries if e.get("releaseDate")]
    entries.sort(key=lambda e: e["releaseDate"], reverse=True)
    entries = entries[:limit]

    ids = [str(e["id"]) for e in entries if e.get("id")]
    preview_map = {}
    if ids:
        try:
            lookup_res = requests.get(
                ITUNES_LOOKUP_URL, params={"id": ",".join(ids), "country": "KR"}, timeout=TIMEOUT
            )
            if lookup_res.ok:
                for r in lookup_res.json().get("results", []):
                    if r.get("trackId"):
                        preview_map[str(r["trackId"])] = r.get("previewUrl")
        except requests.RequestException:
            pass  # 미리듣기 보강만 실패한 것 — 목록 자체는 그대로 반환

    result = [
        {
            "title": e.get("name"),
            "artist": e.get("artistName"),
            "artwork": e.get("artworkUrl100"),
            "previewUrl": preview_map.get(str(e.get("id"))),
            "releaseDate": e.get("releaseDate"),
        }
        for e in entries
    ]
    _cache_set(cache_key, result, NEW_RELEASES_TTL)
    return result
