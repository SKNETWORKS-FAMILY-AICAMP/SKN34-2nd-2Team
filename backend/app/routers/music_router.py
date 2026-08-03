"""GET /music/* — Apple Music(iTunes) 공개 API 프록시.

브라우저(kkbox_customer.html)가 itunes.apple.com / rss.marketingtools.apple.com을
직접 fetch()하면 사용자 네트워크 환경에 따라 CORS나 방화벽 정책으로 막힐 수 있다.
그래서 백엔드가 대신 호출해서 결과만 그대로(또는 가공해서) 돌려준다 — 브라우저는
항상 같은 오리진(localhost:8000)만 호출하므로 CORS 문제 자체가 생기지 않는다.

우리 DB와 무관한 공개 음원 메타데이터라 로그인 여부와 상관없이 열어둔다(require_staff/
require_customer 의존성 없음).
"""
import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
APPLE_CHART_URL = "https://rss.marketingtools.apple.com/api/v2/kr/music/most-played"

TIMEOUT = 6  # seconds — 발표 중 API가 느려도 화면이 무한정 멈추지 않게


@router.get("/search")
def search_track(term: str = Query(..., min_length=1), limit: int = Query(1, ge=1, le=200)):
    """iTunes Search API 그대로 프록시 (응답 형태 동일: {resultCount, results: [...]})."""
    try:
        res = requests.get(
            ITUNES_SEARCH_URL,
            params={"term": term, "country": "KR", "media": "music", "limit": limit},
            timeout=TIMEOUT,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"iTunes 검색 실패: {e}")


@router.get("/chart")
def top_chart(limit: int = Query(100, ge=1, le=200)):
    """Apple Music 공식 대한민국 차트 + iTunes lookup으로 30초 미리듣기 URL 보강해서
    [{rank, title, artist, artwork, previewUrl}, ...] 형태로 반환."""
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

    return [
        {
            "rank": i + 1,
            "title": e.get("name"),
            "artist": e.get("artistName"),
            "artwork": e.get("artworkUrl100"),
            "previewUrl": preview_map.get(str(e.get("id"))),
        }
        for i, e in enumerate(entries)
    ]
