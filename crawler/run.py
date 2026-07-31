"""
혜택맵 통신사 공식 홈페이지 크롤러 — 진입점.

    python3 run.py            # SKT + LG U+ + KT 전부 수집
    python3 run.py skt lguplus  # 일부만 수집

각 통신사 모듈은 common.safe_get() 을 통해서만 HTTP 요청을 보내고,
common.ALLOWED_HOSTS 에 등록된 공식 도메인이 아니면 요청 자체가 예외로 막힌다.
"""
import os
import sys

import common
import skt
import lguplus
import kt
import transform

SITE_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "site", "data", "places.json")

CRAWLERS = {
    "skt": skt.crawl,
    "lguplus": lguplus.crawl,
    "kt": kt.crawl,
}


def main():
    targets = sys.argv[1:] or list(CRAWLERS.keys())
    unknown = [t for t in targets if t not in CRAWLERS]
    if unknown:
        print(f"알 수 없는 대상: {unknown}. 사용 가능: {list(CRAWLERS.keys())}")
        sys.exit(1)

    all_records = []
    for name in targets:
        print(f"\n=== {name} 크롤링 시작 ===")
        try:
            records = CRAWLERS[name]()
        except Exception as e:
            print(f"[{name}] 크롤링 실패: {e}")
            continue
        print(f"[{name}] {len(records)}건 수집")
        all_records.extend(records)

    common.save_json(all_records, "benefits.json")

    print("\n=== 통신사 x 카테고리별 건수 ===")
    from collections import Counter
    counter = Counter((r["carrier"], r["category"]) for r in all_records)
    for (carrier, category), count in sorted(counter.items()):
        print(f"  {carrier} / {category}: {count}건")

    if all_records:
        places = transform.transform(all_records)
        os.makedirs(os.path.dirname(SITE_DATA_PATH), exist_ok=True)
        with open(SITE_DATA_PATH, "w", encoding="utf-8") as f:
            import json
            json.dump(places, f, ensure_ascii=False, indent=2)
        print(f"\n프론트용 데이터 갱신: {SITE_DATA_PATH} (브랜드 {len(places)}개)")


if __name__ == "__main__":
    main()
