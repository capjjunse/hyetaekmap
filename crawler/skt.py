"""
SKT(T멤버십) 크롤러 — 공식: https://sktmembership.tworld.co.kr

'혜택 브랜드' 전체 목록 페이지(list-tab1.do)는 서버사이드 렌더링(JSP)이라
requests + BeautifulSoup 만으로 파싱 가능. 페이지네이션은 pageNum/pageSize
쿼리 파라미터로 동작 (0-base, pageSize=20, 총 개수는 페이지 내 totalCount 로 확인).

한 제휴사 안에 '할인형/적립형/사용형' 등 여러 혜택 라인이 있고, 각 라인마다
등급 배지(VIP/GOLD/SILVER/LITE)가 붙는다. 배지가 VIP 단독으로만 붙은 라인은
'VIP특화혜택'으로, 그 외(등급 무관하게 제공되거나 여러 등급이 함께 명시된 경우)는
'상시혜택'으로 분류한다.

주의: 이 페이지에서는 '월간 혜택(이벤트성 로테이션 혜택)'을 찾지 못했다.
SKT의 월간/이벤트 혜택은 T world 이벤트 섹션 등 별도 영역에 있을 가능성이 높고,
이번 조사에서는 확인하지 못했다 — 필요하면 추가 조사 필요 (TODO).
"""
from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, CATEGORY_ALWAYS, CATEGORY_VIP

BASE_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/benefitbrand/list-tab1.do"
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
    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"SKT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
