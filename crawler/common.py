"""
혜택맵 크롤러 공용 모듈.

반드시 통신사 공식 홈페이지에서만 데이터를 가져오도록 도메인 화이트리스트를
코드 레벨에서 강제한다 (ALLOWED_HOSTS 밖의 URL은 요청 자체가 거부됨).
"""
import re
import time
import json
import datetime
from urllib.parse import urlparse

import requests

ALLOWED_HOSTS = {
    "sktmembership.tworld.co.kr",  # SKT 공식 T멤버십
    "www.lguplus.com",             # LG U+ 공식
    "membership.kt.com",           # KT 공식 멤버십
    "rdi.kt.com",                  # KT 공식 이벤트 정보 API (달달혜택 월간 URL 조회용)
    "app.membership.kt.com",       # KT 공식 멤버십 이벤트 마이크로사이트 (달달혜택 실제 콘텐츠)
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_DELAY_SEC = 1.5   # 요청 사이 최소 간격 (서버 부담 최소화)
REQUEST_TIMEOUT_SEC = 10
MAX_RETRIES = 2

CATEGORY_ALWAYS = "상시혜택"
CATEGORY_MONTHLY = "월간혜택"
CATEGORY_VIP = "VIP특화혜택"

_last_request_at = 0.0


def _throttle():
    global _last_request_at
    elapsed = time.time() - _last_request_at
    if elapsed < REQUEST_DELAY_SEC:
        time.sleep(REQUEST_DELAY_SEC - elapsed)
    _last_request_at = time.time()


def safe_get(url, params=None, headers=None):
    """공식 도메인 화이트리스트를 통과한 URL만 GET 요청을 허용한다."""
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise ValueError(
            f"허용되지 않은 도메인입니다: {host!r}. "
            f"ALLOWED_HOSTS={sorted(ALLOWED_HOSTS)} 만 크롤링할 수 있습니다."
        )

    req_headers = {"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"}
    if headers:
        req_headers.update(headers)

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        _throttle()
        try:
            resp = requests.get(
                url, params=params, headers=req_headers, timeout=REQUEST_TIMEOUT_SEC
            )
            resp.raise_for_status()
            # 서버가 Content-Type에 charset을 안 주면 requests가 ISO-8859-1로
            # 잘못 추정해서 한글이 깨진다 (예: app.membership.kt.com). 그럴 때만
            # chardet 추정치로 보정한다.
            if resp.encoding and resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            return resp
        except requests.RequestException as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"요청 실패: {url} ({last_err})")


def strip_html(text):
    """<br>, <strong> 등 태그를 제거하고 순수 텍스트만 남긴다."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_record(carrier, category, partner, summary, detail="", tier="전체",
                 category_group="", source_url=""):
    return {
        "carrier": carrier,               # SKT / KT / LGU
        "category": category,             # 상시혜택 / 월간혜택 / VIP특화혜택
        "partner": partner,               # 제휴사명
        "benefit_summary": summary,       # 혜택 한줄 요약
        "benefit_detail": detail,         # 상세 조건
        "tier_required": tier,            # 이용 가능 등급
        "category_group": category_group, # 사이트 자체 카테고리(카페/영화관 등)
        "source_url": source_url,
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def save_json(records, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {path} ({len(records)}건)")
