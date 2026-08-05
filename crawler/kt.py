"""
KT 멤버십 크롤러 — 공식: https://membership.kt.com

⚠️ 개발 중 membership.kt.com 이 (WAF로 추정되는) 보안장비 때문에 요청 IP가
   통째로 차단되어 TCP 연결 자체가 안 되는 일이 있었다. 이후 차단이 풀려서
   아래 구조는 실제 응답으로 검증했지만, 또 막힐 수 있으니 너무 자주 돌리지 말 것.

상시혜택 (검증 완료):
  POST https://membership.kt.com/discount/partner/PartnerListHtml.json
       data: daeCode= & pageNo=N & searchName= & jungCode=
  - daeCode 를 비워두면 전체 카테고리가 섞여서 나온다 (총 26페이지 x 6개 = 151개, 확인 시점 기준).
  - Content-Type만 json이고 실제 바디는 HTML 조각.
  - 브랜드: li[data-jungcode] > .sec-cont-tit
  - 혜택 라인: .sec-cont-list li 안에 <em class="color-{tier}">{tier명}</em><span>{설명}</span>
    tier 종류: vvip / vip / gold / general(일반) / all(전등급)
  - 한 브랜드의 라인이 전부 vvip/vip 뿐이면 VIP특화혜택, all/general/gold 라인이
    하나라도 있으면 상시혜택으로 분류.
  - 페이지네이션: 응답 안 <input id="pageTotal" value="N"> 까지.

월간혜택('달달혜택') — 끝까지 조사했지만 안정적인 크롤링은 보류:
  DaldalBenefit.do → event.kt.com/.../ongoing_event_view.html?...pcEvtNo=N (매달 번호가 바뀜)
  → 그 안 iframe으로 app.membership.kt.com/eventpage/evnXXXXXXXXX/kmFesta_web.html
  (역시 매달 URL이 바뀌는 '이달의 KT MEMBERSHIP FESTA' 전용 마이크로사이트) 까지 추적했다.
  문제는:
    1) 1차/2차/3차 쿠폰(배스킨라빈스, 쇼핑라운지 등)은 텍스트가 아니라 배너 '이미지'로만 제공됨.
    2) 문화 행사(뮤지컬/전시) 섹션은 텍스트가 있지만 할인율 숫자가 JS로 애니메이션 카운트업
       되며 채워지는 방식이라 정적 HTML에는 숫자가 아예 없음 (예: "최대", "% 할인"만 있고
       중간 숫자가 빔).
    3) URL 자체가 매달 바뀌는 1회성 이벤트 마이크로사이트라 구조가 유지된다는 보장도 없음.
  → 안정적으로 하려면 Playwright 같은 헤드리스 브라우저로 매달 URL을 새로 찾아 JS 실행까지
    해야 하는데, 지금 GitHub Actions 크론에는 그 정도 무게의 작업은 아직 안 붙였다 (TODO).

VIP특화혜택: 별도 URL 없이 상시혜택 목록 파싱 중 tier 조건으로 자동 분류.
"""
import time
import requests
from bs4 import BeautifulSoup

from common import make_record, strip_html, _throttle as throttle, USER_AGENT, ALLOWED_HOSTS, CATEGORY_ALWAYS, CATEGORY_VIP
from urllib.parse import urlparse

# KT는 SKT/LG U+보다 요청 간격에 훨씬 민감해 보여서(빠르게 몇 번만 쳐도 응답이
# 느려지거나 끊김) 추가로 더 여유를 둔다.
KT_EXTRA_DELAY_SEC = 3.0

CARRIER = "KT"
PARTNER_LIST_URL = "https://membership.kt.com/discount/partner/PartnerList.do"
PARTNER_LIST_API = "https://membership.kt.com/discount/partner/PartnerListHtml.json"

TIER_LABELS = {
    "vvip": "VVIP",
    "vip": "VIP",
    "gold": "GOLD",
    "general": "일반",
    "all": "전등급",
}
VIP_ONLY_TIERS = {"vvip", "vip"}


def _fetch_page(page_no):
    host = urlparse(PARTNER_LIST_API).hostname
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"허용되지 않은 도메인: {host}")

    throttle()
    time.sleep(KT_EXTRA_DELAY_SEC)
    resp = requests.post(
        PARTNER_LIST_API,
        data={"daeCode": "", "pageNo": page_no, "searchName": "", "jungCode": ""},
        headers={
            "User-Agent": USER_AGENT,
            "Referer": PARTNER_LIST_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.text


def _parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for li in soup.select("li[data-jungcode]"):
        name_el = li.select_one(".sec-cont-tit")
        if not name_el:
            continue
        brand = name_el.get_text(strip=True)

        lines = []
        for line in li.select(".sec-cont-list li"):
            em = line.select_one("em")
            span = line.select_one("span")
            if not em or not span:
                continue
            tier_class = next((c.replace("color-", "") for c in em.get("class", []) if c.startswith("color-")), None)
            lines.append((tier_class, strip_html(span.get_text(" ", strip=True))))

        if not lines:
            continue

        tiers_present = {t for t, _ in lines if t}
        is_vip_only = bool(tiers_present) and tiers_present.issubset(VIP_ONLY_TIERS)
        category = CATEGORY_VIP if is_vip_only else CATEGORY_ALWAYS

        for tier_code, desc in lines:
            tier_label = TIER_LABELS.get(tier_code, tier_code or "전체")
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=category,
                    partner=brand,
                    summary=desc,
                    tier=tier_label,
                    source_url=PARTNER_LIST_URL,
                )
            )
    return records


def _total_pages(html):
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one("#pageTotal")
    try:
        return int(el["value"])
    except (TypeError, KeyError, ValueError):
        return 1


def crawl(max_pages=40):
    all_records = []
    total_pages = 1
    page_no = 1
    while page_no <= min(total_pages, max_pages):
        try:
            html = _fetch_page(page_no)
        except requests.RequestException as e:
            print(f"[KT] {page_no}페이지 요청 실패 (서버 차단 가능성): {e}")
            break
        if page_no == 1:
            total_pages = _total_pages(html)
        page_records = _parse_page(html)
        if not page_records:
            break
        all_records.extend(page_records)
        page_no += 1

    if not all_records:
        print("[KT] 수집된 데이터가 없습니다 (서버 차단되었거나 구조가 바뀌었을 수 있음).")
    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"KT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
