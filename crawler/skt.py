"""
SKT(T멤버십) 크롤러 — 공식: https://sktmembership.tworld.co.kr

'혜택 브랜드' 전체 목록 페이지(list-tab1.do)는 서버사이드 렌더링(JSP)이라
requests + BeautifulSoup 만으로 파싱 가능. 페이지네이션은 pageNum/pageSize
쿼리 파라미터로 동작 (0-base, pageSize=20, 총 개수는 페이지 내 totalCount 로 확인).

한 제휴사 안에 '할인형/적립형/사용형' 등 여러 혜택 라인이 있고, 각 라인마다
등급 배지(VIP/GOLD/SILVER/LITE)가 붙는다. 배지가 VIP 단독으로만 붙은 라인은
'VIP특화혜택'으로, 그 외(등급 무관하게 제공되거나 여러 등급이 함께 명시된 경우)는
'상시혜택'으로 분류한다.

월간혜택('T day', 검증 완료):
  GET https://sktmembership.tworld.co.kr/mps/pc-bff/program/tday.do
  - 서버사이드 렌더링. .event-box 하나가 브랜드 1개의 혜택 1건.
  - 브랜드/설명: .tday-info .tit 안에 "브랜드명<br>설명" 형태로 같이 들어있음.
  - 등급 힌트: .tit 위에 <i class="tday*-chance">VIP 찬스</i> 같은 배지가 있으면
    tier 텍스트로 기록 (없으면 "전체"). 그 시점에 진행 중인 회차만 나오므로
    (예: '이번 주만 공개, 다음 주는 Coming Soon') 매일 크롤링하면 자연히 갱신된다.
"""
from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, CATEGORY_ALWAYS, CATEGORY_VIP, CATEGORY_MONTHLY

BASE_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/benefitbrand/list-tab1.do"
TDAY_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/program/tday.do"
CARRIER = "SKT"

TIER_LABELS = {
    "vip": "VIP",
    "gold": "GOLD",
    "silver": "SILVER",
    "lite": "LITE",
}


def _tier_codes(info_div):
    codes = []
    for i in info_div.select(".badge-list i.badge-circle"):
        classes = i.get("class", [])
        for c in classes:
            if c in TIER_LABELS and c not in codes:
                codes.append(c)
    return codes


def _parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for a in soup.select("a.benefit-box"):
        brand_el = a.select_one(".brand")
        if not brand_el:
            continue
        brand = brand_el.get_text(strip=True)

        for dl in a.select(".bnf-info dl"):
            dt = dl.select_one("dt")
            benefit_type = dt.get_text(strip=True) if dt else ""

            for info_div in dl.select("dd .info"):
                tiers = _tier_codes(info_div)
                # 배지(span.badge-list) 를 제외한 순수 설명 텍스트만 추출
                clone = BeautifulSoup(str(info_div), "html.parser")
                badge_span = clone.select_one(".badge-list")
                if badge_span:
                    badge_span.decompose()
                desc = strip_html(clone.get_text(" ", strip=True))
                if not desc:
                    continue

                if tiers == ["vip"]:
                    category = CATEGORY_VIP
                    tier_label = "VIP"
                else:
                    category = CATEGORY_ALWAYS
                    tier_label = "/".join(TIER_LABELS[t] for t in tiers) or "전체"

                records.append(
                    make_record(
                        carrier=CARRIER,
                        category=category,
                        partner=brand,
                        summary=desc,
                        detail=benefit_type,
                        tier=tier_label,
                        category_group="",
                        source_url=BASE_URL,
                    )
                )
    return records


def _total_count(html):
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        if script.string and "totalCount" in script.string:
            for tok in script.string.split(";"):
                if "totalCount" in tok and "=" in tok:
                    try:
                        return int(tok.split("=")[-1].strip())
                    except ValueError:
                        pass
    return None


def _parse_tday(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for box in soup.select(".event-box"):
        tit = box.select_one(".tit")
        if not tit:
            continue
        # "브랜드명<br>설명" -> 줄바꿈 기준으로 브랜드/설명 분리
        parts = [p.strip() for p in tit.decode_contents().split("<br/>")]
        if len(parts) < 2:
            parts = [p.strip() for p in tit.decode_contents().split("<br>")]
        if len(parts) < 2:
            continue
        brand = strip_html(parts[0])
        desc = strip_html("".join(parts[1:]))
        if not brand or not desc:
            continue

        chance = box.select_one('i[class*="chance"]')
        tier = chance.get_text(strip=True) if chance else "전체"

        date_el = box.select_one(".benefit-date")
        detail = date_el.get_text(" ", strip=True) if date_el else ""

        records.append(
            make_record(
                carrier=CARRIER,
                category=CATEGORY_MONTHLY,
                partner=brand,
                summary=desc,
                detail=detail,
                tier=tier,
                category_group="T day",
                source_url=TDAY_URL,
            )
        )
    return records


def crawl_tday():
    resp = safe_get(TDAY_URL)
    return _parse_tday(resp.text)


def crawl(page_size=20, max_pages=20):
    all_records = []
    total = None
    page_num = 0
    while page_num < max_pages:
        resp = safe_get(BASE_URL, params={"pageNum": page_num, "pageSize": page_size})
        if total is None:
            total = _total_count(resp.text)
        page_records = _parse_page(resp.text)
        if not page_records:
            break
        all_records.extend(page_records)
        page_num += 1
        if total is not None and page_num * page_size >= total:
            break

    try:
        all_records.extend(crawl_tday())
    except Exception as e:
        print(f"[SKT] T day 월간혜택 수집 실패: {e}")

    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"SKT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"월간 {sum(1 for r in recs if r['category']==CATEGORY_MONTHLY)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
