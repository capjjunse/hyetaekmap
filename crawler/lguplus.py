"""
LG U+ 크롤러 — 공식: https://www.lguplus.com
(robots.txt 에 Claude 계열 크롤러가 명시적으로 Allow 되어 있음 — /benefit 포함)

세 가지 소스 모두 JSON API라 파싱이 깔끔하다.

1) 상시혜택 / VIP특화혜택
   GET /uhdc/fo/prdv/mebfjnco/v1/jnco
       ?urcMbspDivsCd=01&urcMbspBnftDivsCd={01|02}&urcMbspCatgNo=&pageNo=N&rowSize=50&_paging=true
   - urcMbspBnftDivsCd=02 → 상시혜택 (전체 등급 대상, 등급별로 혜택 크기만 다름)
   - urcMbspBnftDivsCd=01 → VIP콕 (VVIP/VIP 전용)
   - pageNo 를 늘리다가 빈 배열([])이 오면 종료.

2) 월간혜택 ('유플투쁠')
   GET /uhdc/slit/exhibition/v1/section/PCUpTpBenefitListSection?pcMobileDivisionType=PC&osType=ALL
   - data.contentsList 안에 월별 캠페인이 들어있고, 그 중 오늘 날짜가
     exhibitionStartDateTime ~ exhibitionEndDateTime 사이인 항목이 '이번 달 혜택'.
   - contentsDetailList[0].exhibitionContentsHtmlContent 안에 실제 브랜드별
     혜택 카드가 HTML 문자열로 들어있어서 다시 BeautifulSoup으로 파싱해야 함
     (p.date / p.name / p.desc 구조 — CMS 콘텐츠라 다음 달 개편 시 구조가
     바뀔 수 있음, 정기적으로 셀렉터 점검 필요).
"""
import datetime

from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, CATEGORY_ALWAYS, CATEGORY_MONTHLY, CATEGORY_VIP

CARRIER = "LGU"
JNCO_API = "https://www.lguplus.com/uhdc/fo/prdv/mebfjnco/v1/jnco"
MONTHLY_API = "https://www.lguplus.com/uhdc/slit/exhibition/v1/section/PCUpTpBenefitListSection"

BNFT_DIVS_TO_CATEGORY = {
    "02": CATEGORY_ALWAYS,
    "01": CATEGORY_VIP,
}


def _crawl_jnco(bnft_divs_cd, row_size=50, max_pages=20):
    category = BNFT_DIVS_TO_CATEGORY[bnft_divs_cd]
    records = []
    page_no = 1
    while page_no <= max_pages:
        resp = safe_get(
            JNCO_API,
            params={
                "urcMbspDivsCd": "01",
                "urcMbspBnftDivsCd": bnft_divs_cd,
                "urcMbspCatgNo": "",
                "pageNo": page_no,
                "rowSize": row_size,
                "_paging": "true",
            },
        )
        items = resp.json()
        if not items:
            break
        for item in items:
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=category,
                    partner=item.get("urcMbspJncoNm", ""),
                    summary=strip_html(item.get("jncoBnftThumCntn", "")),
                    detail=strip_html(item.get("jncoBnftDetlCntn", "")),
                    tier=item.get("jncoTadvGrdDetlDscr", "") or "전체",
                    category_group=item.get("urcMbspCatgNm", ""),
                    source_url=JNCO_API,
                )
            )
        page_no += 1
    return records


def _crawl_monthly():
    resp = safe_get(MONTHLY_API, params={"pcMobileDivisionType": "PC", "osType": "ALL"})
    data = resp.json().get("data", {})
    contents_list = data.get("contentsList", [])

    now = datetime.datetime.now()
    current = None
    for item in contents_list:
        try:
            start = datetime.datetime.strptime(item["exhibitionStartDateTime"], "%Y-%m-%d %H:%M:%S")
            end = datetime.datetime.strptime(item["exhibitionEndDateTime"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError):
            continue
        if item.get("screenExposureYn") == "Y" and start <= now <= end:
            current = item
            break
    if current is None and contents_list:
        current = contents_list[0]  # fallback: 가장 최근 항목
    if current is None:
        return []

    records = []
    for detail in current.get("contentsDetailList", []):
        html = detail.get("exhibitionContentsHtmlContent", "")
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for li in soup.select("ul li"):
            name_el = li.select_one("p.name")
            desc_el = li.select_one("p.desc")
            date_el = li.select_one("p.date")
            if not name_el or not desc_el:
                continue
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=CATEGORY_MONTHLY,
                    partner=name_el.get_text(strip=True),
                    summary=strip_html(str(desc_el)),
                    detail=f"적용일: {date_el.get_text(strip=True)}" if date_el else "",
                    tier="전체",
                    category_group=current.get("exhibitionContentsNm", "유플투쁠"),
                    source_url="https://www.lguplus.com/benefit-plus",
                )
            )
    return records


def crawl():
    records = []
    records += _crawl_jnco("02")   # 상시혜택
    records += _crawl_jnco("01")   # VIP특화혜택
    records += _crawl_monthly()    # 월간혜택 (유플투쁠)
    return records


if __name__ == "__main__":
    recs = crawl()
    for cat in (CATEGORY_ALWAYS, CATEGORY_VIP, CATEGORY_MONTHLY):
        print(f"LGU+ {cat}: {sum(1 for r in recs if r['category'] == cat)}건")
