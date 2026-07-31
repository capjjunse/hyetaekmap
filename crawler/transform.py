"""
run.py 가 만든 benefits.json(통신사별 원본 레코드)을
프론트(docs/data/places.json)가 바로 소비할 수 있는 '브랜드 단위' 구조로 변환한다.

⚠️ 중요한 한계: 이 데이터는 '어떤 브랜드가 어떤 혜택을 주는지'는 정확하지만,
   '그 브랜드의 매장이 지도 위 정확히 어디 있는지(위도/경도)'는 포함하지 않는다.
   통신사 멤버십 공식 페이지는 브랜드 단위 혜택만 제공하고, 지점별 좌표는 주지 않기
   때문. 실제 지도 핀을 찍으려면 카카오맵 Local API(키워드 장소검색)로 브랜드명별
   지점 좌표를 별도로 조회해서 이 파일과 브랜드명 기준으로 매칭해야 한다 (TODO).

출력 스키마 (docs/data/places.json):
[
  {
    "brand": "CGV",
    "category_group": "영화관",   // 통신사 페이지에 표시된 카테고리(사이트마다 표기가 달라 참고용)
    "benefits": {
      "SKT": { "category": "VIP특화혜택", "tier": "VIP", "summary": "..." } | null,
      "KT":  {...} | null,
      "LGU": {...} | null
    }
  },
  ...
]
"""
import json
import sys
from collections import defaultdict

CARRIER_KEY = {"SKT": "SKT", "KT": "KT", "LGU": "LGU"}


def transform(records):
    grouped = defaultdict(lambda: {"brand": "", "category_group": "", "benefits": {}})

    for r in records:
        brand = r["partner"].strip()
        key = brand
        entry = grouped[key]
        entry["brand"] = brand
        if not entry["category_group"] and r.get("category_group"):
            entry["category_group"] = r["category_group"]

        carrier = CARRIER_KEY.get(r["carrier"])
        if not carrier:
            continue

        existing = entry["benefits"].get(carrier)
        candidate = {
            "category": r["category"],
            "tier": r["tier_required"],
            "summary": r["benefit_summary"],
        }
        # 같은 통신사 안에 여러 혜택 라인이 있으면 상시혜택을 우선 대표값으로 쓰고,
        # 나머지는 all 리스트에 모아둔다.
        if existing is None:
            entry["benefits"][carrier] = {**candidate, "all": [candidate]}
        else:
            existing["all"].append(candidate)
            # 상시혜택이 아직 없으면 상시혜택으로 대표값 교체
            if existing["category"] != "상시혜택" and candidate["category"] == "상시혜택":
                existing["category"] = candidate["category"]
                existing["tier"] = candidate["tier"]
                existing["summary"] = candidate["summary"]

    result = []
    for entry in grouped.values():
        for c in ("SKT", "KT", "LGU"):
            entry["benefits"].setdefault(c, None)
        result.append(entry)

    result.sort(key=lambda e: e["brand"])
    return result


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "benefits.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "../docs/data/places.json"

    with open(src, encoding="utf-8") as f:
        records = json.load(f)

    places = transform(records)

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(places, f, ensure_ascii=False, indent=2)

    carriers_covered = {c: sum(1 for p in places if p["benefits"][c]) for c in ("SKT", "KT", "LGU")}
    print(f"변환 완료: {dst} (브랜드 {len(places)}개)")
    print(f"  통신사별 커버 브랜드 수: {carriers_covered}")


if __name__ == "__main__":
    main()
