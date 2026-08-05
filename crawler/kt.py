"""
KT 멤버십 크롤러 — 공식: https://membership.kt.com

⚠️ membership.kt.com 은 (WAF로 추정되는) 보안장비 때문에 요청 IP가 종종 통째로
   차단된다 — 첫 요청은 성공했다가 바로 다음 요청부터 막히기도 하고, 하루는
   멀쩡하다가 다음 날은 막히기도 했다 (GitHub Actions IP에서도 재현됨). 그래서
   run.py 쪽에 '이번에 0건이면 직전 데이터 유지' 안전장치를 넣어뒀다 — 크롤러
   자체는 그대로 두고 너무 자주/빨리 재시도하지 않는 게 최선이다.

상시혜택 (검증 완료):
  POST https://membership.kt.com/discount/partner/PartnerListHtml.json
       data: daeCode= & pageNo=N & searchName= & jungCode=
  - daeCode 를 비워두면 전체 카테고리가 섞여서 나온다 (총 26페이지 x 6개 = 151개, 확인 시점 기준).
  - Content-Type만 json이고 실제 바디는 HTML 조각.
  - 브랜드: li[data-jungcode] > .sec-cont-tit
  - 혜택 라인: .sec-cont-list li 안에 <em class="color-{tier}">{tier명}</em><span>{설명}</span>
    tier 종류: vvip / vip / gold / general(일반) / all(전등급) — 이건 '이 라인을
    어느 등급이 쓸 수 있는지'일 뿐이라 전부 상시혜택으로 기록한다 (등급 조건과
    VIP초이스라는 별도 프로그램은 다른 개념 — 아래 참고).
  - 페이지네이션: 응답 안 <input id="pageTotal" value="N"> 까지.

VIP특화혜택('VVIP/VIP 초이스', 검증 완료):
  POST https://membership.kt.com/vip/choice/VvipChoiceListHtml.json  (VVIP, Referer: .../vip/choice/VvipChoiceInfo.do)
  POST https://membership.kt.com/vip/choice/VipListHtml.json         (VIP,  Referer: .../vip/choice/ChoiceInfo.do)
  - 둘 다 body 없이 POST만 하면 됨 (Referer/X-Requested-With 헤더는 유지).
  - ul.double-discount-list > li 가 브랜드 요약 카드, 바로 다음 형제
    li.view-detail 안에 .discount-detail > li 로 혜택/이용횟수/이용안내가
    나뉘어 있다 — 이 중 alt="혜택" 줄의 텍스트를 설명으로 쓴다(요약 카드보다 더
    구체적인 경우가 많음). 브랜드명은 h3.tit.

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
VVIP_CHOICE_PAGE = "https://membership.kt.com/vip/choice/VvipChoiceInfo.do"
VVIP_CHOICE_API = "https://membership.kt.com/vip/choice/VvipChoiceListHtml.json"
VIP_CHOICE_PAGE = "https://membership.kt.com/vip/choice/ChoiceInfo.do"
VIP_CHOICE_API = "https://membership.kt.com/vip/choice/VipListHtml.json"

TIER_LABELS = {
    "vvip": "VVIP",
    "vip": "VIP",
    "gold": "GOLD",
    "general": "일반",
    "all": "전등급",
}


def _post(url, referer):
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"허용되지 않은 도메인: {host}")
    throttle()
    time.sleep(KT_EXTRA_DELAY_SEC)
    resp = requests.post(
        url,
        data={"daeCode": "", "pageNo": 1, "searchName": "", "jungCode": ""} if url == PARTNER_LIST_API else {},
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.text


def _fetch_partner_page(page_no):
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


def _parse_partner_page(html):
    """상시혜택. 등급 배지는 '이용 가능 등급' 정보로만 쓰고, 카테고리는 항상
    상시혜택으로 기록한다 (VVIP/VIP 초이스라는 별도 프로그램과 혼동 금지)."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for li in soup.select("li[data-jungcode]"):
        name_el = li.select_one(".sec-cont-tit")
        if not name_el:
            continue
        brand = name_el.get_text(strip=True)

        for line in li.select(".sec-cont-list li"):
            em = line.select_one("em")
            span = line.select_one("span")
            if not em or not span:
                continue
            tier_class = next((c.replace("color-", "") for c in em.get("class", []) if c.startswith("color-")), None)
            desc = strip_html(span.get_text(" ", strip=True))
            if not desc:
                continue
            tier_label = TIER_LABELS.get(tier_class, tier_class or "전체")
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=CATEGORY_ALWAYS,
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


def _parse_choice(html, tier_label, page_url):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for a in soup.select("ul.double-discount-list > li > a"):
        h3 = a.select_one(".double-name h3.tit")
        if not h3:
            continue
        brand = h3.get_text(strip=True)

        li = a.parent
        detail_li = li.find_next_sibling("li", class_="view-detail")
        desc = None
        if detail_li:
            for row in detail_li.select(".discount-detail > li"):
                img = row.select_one(".tit img")
                if img and img.get("alt") == "혜택":
                    p = row.select_one(".text")
                    if p:
                        desc = strip_html(p.get_text(" ", strip=True))
        if not desc:
            # 상세 블록을 못 찾으면 요약 카드 텍스트로 대체
            dn = a.select_one(".double-name")
            desc = strip_html(dn.get_text(" ", strip=True).replace(brand, "", 1)) if dn else None
        if not brand or not desc:
            continue

        records.append(
            make_record(
                carrier=CARRIER,
                category=CATEGORY_VIP,
                partner=brand,
                summary=desc,
                tier=tier_label,
                category_group=f"{tier_label} 초이스",
                source_url=page_url,
            )
        )
    return records


def crawl_partner_list(max_pages=40):
    all_records = []
    total_pages = 1
    page_no = 1
    while page_no <= min(total_pages, max_pages):
        try:
            html = _fetch_partner_page(page_no)
        except requests.RequestException as e:
            print(f"[KT] 상시혜택 {page_no}페이지 요청 실패 (서버 차단 가능성): {e}")
            break
        if page_no == 1:
            total_pages = _total_pages(html)
        page_records = _parse_partner_page(html)
        if not page_records:
            break
        all_records.extend(page_records)
        page_no += 1
    return all_records


def crawl_vip_choice():
    records = []
    for tier_label, api_url, page_url in (
        ("VVIP", VVIP_CHOICE_API, VVIP_CHOICE_PAGE),
        ("VIP", VIP_CHOICE_API, VIP_CHOICE_PAGE),
    ):
        try:
            html = _post(api_url, referer=page_url)
            records.extend(_parse_choice(html, tier_label, page_url))
        except requests.RequestException as e:
            print(f"[KT] {tier_label} 초이스 요청 실패 (서버 차단 가능성): {e}")
    return records


def crawl(max_pages=40):
    all_records = crawl_partner_list(max_pages=max_pages)
    all_records.extend(crawl_vip_choice())

    if not all_records:
        print("[KT] 수집된 데이터가 없습니다 (서버 차단되었거나 구조가 바뀌었을 수 있음).")
    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"KT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
