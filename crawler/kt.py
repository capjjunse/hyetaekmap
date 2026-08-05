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

월간혜택('달달혜택', 검증 완료):
  DaldalBenefit.do 안의 event.kt.com 링크에서 정규식으로 pcEvtNo만 뽑아내고,
  그 번호로 KT 공식 이벤트 API를 바로 호출한다 (event.kt.com 자체는 JS SPA라
  안 거쳐도 됨):
    GET https://rdi.kt.com/kt/events/v1.0/{pcEvtNo}?type=P
    -> JSON. data.evnInfo.apctUrl 이 '이달의 KT MEMBERSHIP FESTA' 마이크로사이트
       주소 (예: https://app.membership.kt.com/eventpage/evn879840107/kmFesta_web.html,
       매달 URL이 바뀌지만 이 API가 항상 최신 주소를 알려준다).
  그 페이지 안:
    - 쿠폰 라운드(1차/2차/3차): .round 하나가 회차 1개. .box a img 의 alt 속성에
      "브랜드 레디팩 30% 할인 정상가 10,800원, 할인가 7,560원"처럼 설명이 통째로
      들어있다 (처음엔 배너 '이미지'라 텍스트가 없는 줄 알았는데, alt 텍스트에
      다 있었다). 브랜드명은 <a href="javascript:fnMovPage('id','브랜드명')">
      의 두 번째 인자에서 뽑고, 못 뽑으면 alt 텍스트 앞부분(숫자 나오기 전까지)으로
      추정한다. 아직 공개 안 된 회차는 .box.soon "COMING SOON"만 있어 건너뛴다.
    - 문화 행사(뮤지컬/전시): #section04 안 li 하나가 1건. h3(뮤지컬/전시)+p(작품명)
      +span(할인율)이 전부 정적 HTML에 있다 (애니메이션 카운트업은 화면 표시용
      이펙트일 뿐 최종 값은 소스에 이미 박혀 있었다).
"""
import re
import time
import requests
from bs4 import BeautifulSoup

from common import safe_get, make_record, strip_html, _throttle as throttle, USER_AGENT, ALLOWED_HOSTS, CATEGORY_ALWAYS, CATEGORY_VIP, CATEGORY_MONTHLY
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
DALDAL_PAGE = "https://membership.kt.com/discount/benefit/DaldalBenefit.do"
EVENT_API_TMPL = "https://rdi.kt.com/kt/events/v1.0/{evt_no}?type=P"

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
    if resp.encoding and resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
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
    if resp.encoding and resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
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


def _extract_coupon_brand(href, alt):
    m = re.search(r"fnMov(?:Page|CouponPage|DetailPage)\('[^']*',\s*'([^']*)'", href or "")
    candidate = (m.group(1) or "").strip() if m else ""
    if candidate and re.search(r"[가-힣]", candidate) and not re.fullmatch(r"[A-Z0-9_]+", candidate):
        return candidate
    # 코드성 id라 브랜드명이 아니면 alt 텍스트에서 숫자/할인 나오기 전까지를 브랜드로 추정
    m2 = re.match(r"^([^\d%]+)", alt or "")
    guess = (m2.group(1).strip() if m2 else "") or (alt or "").strip()
    return guess


def _parse_daldal(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for round_el in soup.select(".round"):
        tag_el = round_el.select_one(".tag")
        period_el = round_el.select_one(".period")
        round_label = tag_el.get_text(strip=True) if tag_el else ""
        period_txt = period_el.get_text(" ", strip=True) if period_el else ""
        for a in round_el.select(".box a"):
            img = a.select_one("img[alt]")
            if not img or not img.get("alt"):
                continue
            alt = img["alt"].strip()
            brand = _extract_coupon_brand(a.get("href", ""), alt)
            if not brand:
                continue
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=CATEGORY_MONTHLY,
                    partner=brand,
                    summary=strip_html(alt),
                    detail=f"달달혜택 {round_label} {period_txt}".strip(),
                    tier="전체",
                    category_group="달달혜택",
                    source_url=DALDAL_PAGE,
                )
            )

    culture = soup.select_one("#section04")
    if culture:
        for li in culture.select("ul > li"):
            h3 = li.select_one(".detail h3")
            p = li.select_one(".detail p")
            span = li.select_one(".detail span")
            if not p or not span:
                continue
            kind = h3.get_text(strip=True) if h3 else ""
            title = p.get_text(strip=True)
            brand = f"{kind} {title}".strip() if kind else title
            desc = strip_html(span.get_text(" ", strip=True))
            if not brand or not desc:
                continue
            records.append(
                make_record(
                    carrier=CARRIER,
                    category=CATEGORY_MONTHLY,
                    partner=brand,
                    summary=desc,
                    detail="달달혜택 문화 행사",
                    tier="전체",
                    category_group="달달혜택",
                    source_url=DALDAL_PAGE,
                )
            )
    return records


def crawl_daldal():
    resp = safe_get(DALDAL_PAGE)
    m = re.search(r"event\.kt\.com/[^\"'\s)]*pcEvtNo=(\d+)", resp.text)
    if not m:
        print("[KT] 달달혜택: DaldalBenefit.do 안에서 이벤트 번호(pcEvtNo)를 못 찾았습니다.")
        return []
    evt_no = m.group(1)

    event_resp = safe_get(EVENT_API_TMPL.format(evt_no=evt_no))
    apct_url = event_resp.json().get("data", {}).get("evnInfo", {}).get("apctUrl")
    if not apct_url:
        print(f"[KT] 달달혜택: 이벤트 API 응답에서 이달의 페이지 주소를 못 찾았습니다 (evtNo={evt_no}).")
        return []

    page_resp = safe_get(apct_url)
    return _parse_daldal(page_resp.text)


def crawl(max_pages=40):
    all_records = crawl_partner_list(max_pages=max_pages)
    all_records.extend(crawl_vip_choice())
    try:
        all_records.extend(crawl_daldal())
    except Exception as e:
        print(f"[KT] 달달혜택 수집 실패: {e}")

    if not all_records:
        print("[KT] 수집된 데이터가 없습니다 (서버 차단되었거나 구조가 바뀌었을 수 있음).")
    return all_records


if __name__ == "__main__":
    recs = crawl()
    print(f"KT: {len(recs)}건 수집 (상시 {sum(1 for r in recs if r['category']==CATEGORY_ALWAYS)} / "
          f"VIP {sum(1 for r in recs if r['category']==CATEGORY_VIP)})")
