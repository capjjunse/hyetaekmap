"""
KT 멤버십 크롤러 — 공식: https://membership.kt.com

⚠️ 개발 중 확인된 문제: membership.kt.com 은 짧은 시간 안에 반복 요청하면
   (WAF로 추정되는) 서버가 이후 요청을 아예 타임아웃시켜 버린다.
   이 파일 작성 시점에는 최초 1회만 정상 응답(200)을 받았고, 이후 재시도는
   모두 연결 타임아웃으로 실패했다. 그래서 아래 셀렉터(BeautifulSoup 부분)는
   실제 목록 HTML 구조를 끝까지 확인하지 못한 '최선의 추정' 상태다.

   → 실행 전에 반드시 아래를 먼저 확인할 것:
     1. 이 스크립트를 너무 자주 돌리지 말 것 (하루 1회 이하 권장, REQUEST_DELAY_SEC 를
        common.py 보다 더 크게 잡는 것도 고려).
     2. 실행 후 records 가 비어 있으면 셀렉터가 실제 구조와 다르다는 뜻이니,
        PAGE_URLS 를 직접 브라우저로 열어 HTML 구조를 보고 CSS 셀렉터를 맞춰줘야 한다.
     3. 계속 차단된다면 크롤링 대신 KT 측에 제휴/데이터 이용 문의를 하는 것을 권장.

대상 페이지:
  - 상시혜택: https://membership.kt.com/discount/partner/PartnerList.do (제휴 브랜드)
  - 월간혜택: https://membership.kt.com/discount/benefit/DaldalBenefit.do (달달혜택)
  - VIP특화혜택: 확인된 별도 URL 없음 — 제휴 브랜드 페이지 안에 등급별 조건이
    함께 표시될 가능성이 높음 (SKT 사례처럼). PartnerList.do 파싱 시 등급 뱃지가
    보이면 그 기준으로 상시/VIP 를 나눌 것.
"""
from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, CATEGORY_ALWAYS, CATEGORY_MONTHLY, CATEGORY_VIP

CARRIER = "KT"
PARTNER_LIST_URL = "https://membership.kt.com/discount/partner/PartnerList.do"
MONTHLY_URL = "https://membership.kt.com/discount/benefit/DaldalBenefit.do"


def _guess_parse_partner_list(html):
    """TODO: 실제 HTML을 받아본 뒤 셀렉터를 검증/수정할 것 (아래는 추정치)."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    candidates = soup.select(".partner-list li, .brand-list li, ul.list-partner > li")
    for li in candidates:
        name_el = li.select_one(".name, .brand, strong")
        desc_el = li.select_one(".desc, .benefit, p")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        desc = strip_html(desc_el.get_text(" ", strip=True)) if desc_el else ""
        tier_el = li.select_one(".grade, .badge, .tier")
        tier = tier_el.get_text(strip=True) if tier_el else "전체"
        category = CATEGORY_VIP if "VIP" in tier.upper() and "전체" not in tier else CATEGORY_ALWAYS
        records.append(
            make_record(
                carrier=CARRIER,
                category=category,
                partner=name,
                summary=desc,
                tier=tier,
                source_url=PARTNER_LIST_URL,
            )
        )
    return records


def _guess_parse_monthly(html):
    """TODO: 달달혜택 페이지 실제 구조 확인 후 셀렉터 보정."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    candidates = soup.select(".benefit-list li, .event-list li, ul.list-benefit > li")
    for li in candidates:
        name_el = li.select_one(".name, .brand, strong")
        desc_el = li.select_one(".desc, .benefit, p")
        if not name_el:
            continue
        records.append(
            make_record(
                carrier=CARRIER,
                category=CATEGORY_MONTHLY,
                partner=name_el.get_text(strip=True),
                summary=strip_html(desc_el.get_text(" ", strip=True)) if desc_el else "",
                tier="전체",
                category_group="달달혜택",
                source_url=MONTHLY_URL,
            )
        )
    return records


def crawl():
    records = []
    try:
        resp = safe_get(PARTNER_LIST_URL)
        records += _guess_parse_partner_list(resp.text)
    except RuntimeError as e:
        print(f"[KT] 상시혜택 수집 실패 (서버 차단 가능성): {e}")

    try:
        resp = safe_get(MONTHLY_URL)
        records += _guess_parse_monthly(resp.text)
    except RuntimeError as e:
        print(f"[KT] 월간혜택 수집 실패 (서버 차단 가능성): {e}")

    if not records:
        print("[KT] 수집된 데이터가 없습니다. 셀렉터를 실제 HTML 구조에 맞게 수정하세요.")
    return records


if __name__ == "__main__":
    recs = crawl()
    print(f"KT: {len(recs)}건 수집")
