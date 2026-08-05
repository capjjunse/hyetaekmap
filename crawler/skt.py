"""
SKT(T멤버십) 크롤러 — 공식: https://sktmembership.tworld.co.kr

세 가지 혜택은 사이트에서 서로 다른(=독립적인) 페이지로 제공된다. 한 페이지 안에서
등급 배지만 보고 카테고리를 추측하지 말고, 반드시 아래 각각의 URL에서만 가져온다.

상시혜택 (검증 완료):
  GET https://sktmembership.tworld.co.kr/mps/pc-bff/benefitbrand/list-tab1.do?pageNum=N&pageSize=20
  - 서버사이드 렌더링. a.benefit-box 하나가 브랜드 1개.
  - 한 브랜드 안에 '할인형/적립형/사용형' 등 여러 혜택 라인이 있고, 각 라인마다
    등급 배지(VIP/GOLD/SILVER/LITE)가 붙는다 — 이건 '이 라인을 어느 등급이 쓸 수
    있는지'일 뿐, 전부 상시혜택이다 (등급별로 조건이 다른 것과 별도 VIP 전용
    프로그램인 것은 다른 개념 — 아래 VIP Pick 참고).
  - (참고) list-tab2.do 도 사용자가 '상시혜택'으로 알려줬지만 실제로 열어보면
    혜택 설명 없이 브랜드명 183개만 있는 색인 목록이라, 실제 내용이 있는 tab1을 쓴다.

월간혜택('T day', 검증 완료):
  GET https://sktmembership.tworld.co.kr/mps/pc-bff/program/tday.do
  - 서버사이드 렌더링. .event-box 하나가 브랜드 1개의 혜택 1건.
  - 브랜드/설명: .tday-info .tit 안에 "브랜드명<br>설명" 형태로 같이 들어있음.
  - 그 시점에 진행 중인 회차만 나오므로(예: '이번 주만 공개, 다음 주는 Coming
    Soon') 매일 크롤링하면 자연히 갱신된다.

VIP특화혜택('VIP Pick', 검증 완료):
  GET https://sktmembership.tworld.co.kr/mps/pc-bff/program/vippick.do
  - 서버사이드 렌더링. ul.benefit-list > li 하나가 혜택 1건 (매달 1개만 선택
    이용 가능한 'PICK' 프로그램 — 상시혜택 안에 있는 'VIP 등급도 쓸 수 있는 라인'
    과는 다른, SKT가 별도로 운영하는 전용 프로그램).
  - 브랜드명은 각 li 안 hidden input[name=xtr] 값(파이프(|)로 구분된 필드, 6번째
    필드)에 들어있다. 예: "1374|V757|2001||5521|CGV|movie|0|null|0" -> CGV
  - 설명: .text-info 의 텍스트.
"""
from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, CATEGORY_ALWAYS, CATEGORY_VIP, CATEGORY_MONTHLY

BASE_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/benefitbrand/list-tab1.do"
TDAY_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/program/tday.do"
VIPPICK_URL = "https://sktmembership.tworld.co.kr/mps/pc-bff/program/vippick.do"
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
    """상시혜택 (list-tab1.do). 등급 배지는 '이용 가능 등급' 정보로만 쓰고,
    카테고리는 항상 상시혜택으로 기록한다 (VIP Pick과 혼동 금지)."""
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
                clone = BeautifulSoup(str(info_div), "html.parser")
                badge_span = clone.select_one(".badge-list")
                if badge_span:
                    badge_span.decompose()
                desc = strip_html(clone.get_text(" ", strip=True))
                if not desc:
                    continue

                tier_label = "/".join(TIER_LABELS[t] for t in tiers) or "전체"
                records.append(
                    make_record(
                        carrier=CARRIER,
                        category=CATEGORY_ALWAYS,
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


def _parse_vippick(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for li in soup.select("ul.benefit-list > li"):
        xtr = li.select_one('input[name="xtr"]')
        text_info = li.select_one(".text-info")
        if not xtr or not text_info:
            continue
        parts = xtr.get("value", "").split("|")
        brand = parts[5].strip() if len(parts) > 5 else ""
        desc = strip_html(text_info.get_text(" ", strip=True))
        if not brand or not desc:
            continue
        records.append(
            make_record(
                carrier=CARRIER,
                category=CATEGORY_VIP,
                partner=brand,
                summary=desc,
                tier="VIP",
                category_group="VIP Pick",
                source_url=VIPPICK_URL,
            )
        )
    return records


def crawl_tday():
    resp = safe_get(TDAY_URL)
    return _parse_tday(resp.text)


def crawl_vippick():
    resp = safe_get(VIPPICK_URL)
    return _parse_vippick(resp.text)


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

    for label, fn in (("T day 월간혜택", crawl_tday), ("VIP Pick", crawl_vippick)):
        try:
            all_records.extend(fn())
        except Exception as e:
            print(f"[SKT] {label} 수집 실패: {e}")

    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"SKT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"월간 {sum(1 for r in recs if r['category']==CATEGORY_MONTHLY)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
