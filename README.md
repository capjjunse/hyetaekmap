# 혜택맵

카카오맵 위에서 제휴사를 누르면 SKT · KT · LG U+ 멤버십 혜택을 보여주는 앱의 디자인 프로토타입 + 통신사 공식 홈페이지 혜택 크롤러.

## 구조

```
crawler/        통신사 공식 홈페이지 크롤러 (SKT / LG U+ / KT)
docs/           프론트 프로토타입 (docs/index.html) — GitHub Pages가 여기서 서빙
docs/data/      크롤러가 생성하는 실데이터 (places.json) — GitHub Actions가 매일 자동 갱신
.github/workflows/update-benefits.yml   매일 크롤링 → 데이터 갱신 → 자동 커밋
```

## 크롤러 실행

```bash
cd crawler
pip install -r requirements.txt
python run.py            # SKT + LG U+ + KT 전부
python run.py skt lguplus  # 일부만
```

실행하면 `crawler/benefits.json`(원본)과 `docs/data/places.json`(프론트용, 브랜드 단위로 통신사 3사 데이터를 합친 것)이 갱신됩니다.

**반드시 아래 공식 페이지에서만 크롤링합니다** (도메인은 `crawler/common.py`의 `ALLOWED_HOSTS`로 코드 레벨에서 강제, 그 외 도메인은 요청 자체가 거부됨). 카테고리(상시/월간/VIP특화)는 사이트가 실제로 분리해서 제공하는 페이지 기준으로 나눈 것이지, 등급 배지를 보고 추측한 게 아닙니다.

| | 상시혜택 | 월간혜택 | VIP특화혜택 |
|---|---|---|---|
| **SKT** | [benefitbrand/list-tab1.do](https://sktmembership.tworld.co.kr/mps/pc-bff/benefitbrand/list-tab1.do) | [program/tday.do](https://sktmembership.tworld.co.kr/mps/pc-bff/program/tday.do) (T day) | [program/vippick.do](https://sktmembership.tworld.co.kr/mps/pc-bff/program/vippick.do) (VIP Pick) |
| **KT** | [discount/partner/PartnerList.do](https://membership.kt.com/discount/partner/PartnerList.do) | 보류 (아래 한계 참고) | [vip/choice/VvipChoiceInfo.do](https://membership.kt.com/vip/choice/VvipChoiceInfo.do) + [ChoiceInfo.do](https://membership.kt.com/vip/choice/ChoiceInfo.do) (VVIP/VIP 초이스) |
| **LG U+** | [benefit-membership](https://www.lguplus.com/benefit-membership)?...BnftDivsCd=02 | [benefit-plus](https://www.lguplus.com/benefit-plus) (유플투쁠) | 같은 페이지 ?...BnftDivsCd=01 (VIP콕) |

### 알려진 한계

- **KT 전체**: 반복 요청 시 서버가 요청 IP를 통째로 차단하는 일이 있습니다 (WAF 추정 — GitHub Actions IP에서도 재현됨, 하루는 되고 하루는 막히는 식). `run.py`가 이번 크롤링이 0건이면 직전 데이터를 그대로 유지하도록 안전장치를 넣어뒀지만, 근본적으로는 KT 쪽에 데이터 이용 문의를 하는 게 안전할 수 있습니다.
- **KT 월간혜택('달달혜택')**: 실제 콘텐츠가 매달 URL이 바뀌는 이벤트 마이크로사이트 안에 있고, 일부는 이미지 배너로만·일부는 숫자가 JS 애니메이션으로 채워지는 방식이라 안정적인 텍스트 크롤링이 어려워 보류했습니다. 자세한 내용은 `crawler/kt.py` 상단 주석 참고.
- **지도 핀 매칭**: 통신사 공식 페이지는 브랜드 단위 혜택만 제공하고 지점별 좌표는 주지 않습니다. 그래서 지도 탭은 카카오맵 카테고리 검색(음식점/카페/편의점/문화시설/대형마트)으로 현재 화면 범위의 실제 매장을 가져온 뒤, 이름이 `docs/data/places.json`의 브랜드와 일치하는 곳만 핀으로 표시합니다 — 온라인 전용 브랜드(11번가, 앱 구독 등)는 지도에는 안 뜨고 혜택 탭에서만 보입니다.

## GitHub Pages로 배포하기

1. 이 저장소를 GitHub에 올린 뒤, Settings → Pages → Source를 `main` 브랜치 `/docs` 폴더로 설정
2. `https://<계정>.github.io/<repo>/` 로 접속하면 최신 `docs/data/places.json`을 자동으로 불러옵니다
3. `.github/workflows/update-benefits.yml`이 매일 자동으로 크롤링 → 데이터 갱신 → 커밋 → Pages 재배포까지 이어집니다 (Actions 탭에서 수동 실행도 가능)
