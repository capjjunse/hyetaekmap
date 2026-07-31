# 혜택맵

카카오맵 위에서 제휴사를 누르면 SKT · KT · LG U+ 멤버십 혜택을 보여주는 앱의 디자인 프로토타입 + 통신사 공식 홈페이지 혜택 크롤러.

## 구조

```
crawler/        통신사 공식 홈페이지 크롤러 (SKT / LG U+ / KT)
site/           프론트 프로토타입 (site/index.html)
site/data/      크롤러가 생성하는 실데이터 (places.json) — GitHub Actions가 매일 자동 갱신
.github/workflows/update-benefits.yml   매일 크롤링 → 데이터 갱신 → 자동 커밋
```

## 크롤러 실행

```bash
cd crawler
pip install -r requirements.txt
python run.py            # SKT + LG U+ + KT 전부
python run.py skt lguplus  # 일부만
```

실행하면 `crawler/benefits.json`(원본)과 `site/data/places.json`(프론트용, 브랜드 단위로 통신사 3사 데이터를 합친 것)이 갱신됩니다.

**반드시 각 통신사 공식 도메인에서만 크롤링하도록** `crawler/common.py`의 `ALLOWED_HOSTS`에 없는 도메인은 요청 자체가 거부됩니다.

- SKT: `sktmembership.tworld.co.kr`
- LG U+: `www.lguplus.com`
- KT: `membership.kt.com`

### 알려진 한계

- **KT**: 반복 요청 시 서버가 요청 IP를 통째로 차단하는 것으로 보입니다 (WAF 추정 — Playwright로 실제 브라우저를 띄워도 TCP 연결 자체가 안 됨). 로컬 네트워크에서 낮은 빈도로 실행해보시고, 계속 막히면 KT에 데이터 이용 문의를 권장합니다. `crawler/kt.py`의 파싱 셀렉터는 실제 페이지를 끝까지 확인하지 못해 추정치입니다.
- **SKT 월간 혜택**: 아직 소스를 찾지 못했습니다 (상시혜택/VIP특화혜택만 확인).
- **지도 핀 좌표 없음**: 통신사 공식 페이지는 브랜드 단위 혜택만 제공하고 지점별 좌표(위도/경도)는 주지 않습니다. 그래서 `site/data/places.json`은 혜택 탭(리스트)에서만 쓰이고, 지도 탭의 핀은 여전히 데모용 목데이터입니다. 실제 지도에 연결하려면 카카오맵 Local API로 브랜드별 지점 좌표를 추가로 조회해서 브랜드명 기준으로 매칭해야 합니다.

## GitHub Pages로 배포하기

1. 이 저장소를 GitHub에 올린 뒤, Settings → Pages → Source를 `main` 브랜치 `/site` 폴더로 설정
2. `https://<계정>.github.io/<repo>/` 로 접속하면 최신 `site/data/places.json`을 자동으로 불러옵니다
3. `.github/workflows/update-benefits.yml`이 매일 자동으로 크롤링 → 데이터 갱신 → 커밋 → Pages 재배포까지 이어집니다 (Actions 탭에서 수동 실행도 가능)
