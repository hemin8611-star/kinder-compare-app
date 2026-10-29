"""
터미널 대화형 쿠팡 파트너스 큐레이션 상품 관리 도구 (쿠팡상품관리.py)
- 사용법: 터미널에서 `python 쿠팡상품관리.py` 실행
- 기능:
  1) 현재 등록된 4개 상품(cp-1 ~ cp-4) 목록 확인
  2) 쿠팡 파트너스 위젯 주소(https://coupa.ng/... 또는 https://partners.coupangcdn.com/...)만 붙여넣으면
     상품명, 썸네일 이미지 주소, 파트너스 이동 링크를 자동 추출하여 data.js 에 문법 오류 없이 즉시 반영!
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_JS_PATH = os.path.join(BASE_DIR, "data.js")


def load_coupang_curation():
    with open(DATA_JS_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"const COUPANG_CURATION = (\{.*?\});\s*const ADMISSION_GUIDE_DATA", content, re.S)
    if not m:
        raise ValueError("data.js에서 COUPANG_CURATION 블록을 찾을 수 없습니다.")
    return content, json.loads(m.group(1))


def save_coupang_curation(full_content, curation_obj):
    new_json_str = json.dumps(curation_obj, ensure_ascii=False, indent=2)
    updated = re.sub(
        r"const COUPANG_CURATION = \{.*?\};\s*(?=const ADMISSION_GUIDE_DATA)",
        f"const COUPANG_CURATION = {new_json_str};\n\n",
        full_content,
        count=1,
        flags=re.S,
    )
    with open(DATA_JS_PATH, "w", encoding="utf-8") as f:
        f.write(updated)


def parse_widget_or_url(raw_input):
    raw_input = raw_input.strip()
    m_src = re.search(r'src=["\']([^"\']+)["\']', raw_input)
    if m_src:
        raw_input = m_src.group(1)

    if "coupa.ng/" in raw_input:
        try:
            req = urllib.request.Request(
                raw_input,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_input = resp.geturl()
        except Exception as e:
            print(f"[안내] coupa.ng 자동 변환 중 참고: {e}")

    parsed = urllib.parse.urlparse(raw_input)
    qs = urllib.parse.parse_qs(parsed.query)

    link_url = qs.get("linkUrl", [""])[0] or raw_input
    prod_img = qs.get("productImage", [""])[0]
    prod_desc = qs.get("productDescription", [""])[0]

    if "%2F" in link_url or "%3F" in link_url:
        link_url = urllib.parse.unquote(link_url)
    if "&productImage=" in link_url:
        link_url = link_url.split("&productImage=")[0]
    idx = link_url.find("link.coupang.com")
    if idx >= 0 and not link_url.startswith("http"):
        link_url = "https://" + link_url[idx:]

    return {
        "url": link_url,
        "image": prod_img,
        "name": prod_desc,
    }


def main():
    content, curation = load_coupang_curation()
    items = curation.get("items", [])

    print("\n" + "=" * 65)
    print(" 🎒 [유치원콕] 터미널 쿠팡 파트너스 상품 관리 도구")
    print("=" * 65)
    for idx, it in enumerate(items, 1):
        print(f" [{idx}] ({it['id']}) [{it['badge']}] {it['name']} | {it['price']}")
    print("-" * 65)

    choice = input("수정할 상품 번호(1~4)를 입력하세요 (종료하려면 Enter): ").strip()
    if not choice:
        print("종료합니다.")
        return
    if not choice.isdigit() or not (1 <= int(choice) <= len(items)):
        print("올바른 번호(1~4)를 입력해 주세요.")
        return

    slot_idx = int(choice) - 1
    target = items[slot_idx]
    print(f"\n👉 선택된 슬롯: [{slot_idx+1}] {target['name']} ({target['price']})")

    raw_url = input("\n1) 쿠팡 주소(coupa.ng, 위젯 주소, 또는 link.coupang.com)를 붙여넣으세요:\n> ").strip()
    if raw_url:
        extracted = parse_widget_or_url(raw_url)
        if extracted["url"]:
            target["url"] = extracted["url"]
        if extracted["image"]:
            target["image"] = extracted["image"]
            print("  ✓ 썸네일 이미지 자동 추출 완료!")
        if extracted["name"]:
            print(f"  ✓ 추출된 상품명: {extracted['name']}")
            use_name = input("  이 상품명을 그대로 사용할까요? (Enter=예 / 직접 입력 시 변경): ").strip()
            target["name"] = use_name if use_name else extracted["name"]
        else:
            new_name = input(f"2) 상품명 입력 (현재: {target['name']}): ").strip()
            if new_name:
                target["name"] = new_name

    new_price = input(f"\n3) 표시할 가격 입력 (예: 8,900원 / 현재: {target['price']}): ").strip()
    if new_price:
        if not new_price.endswith("원"):
            new_price += "원"
        target["price"] = new_price

    new_desc = input(f"\n4) 한 줄 설명 입력 (Enter 누르면 현재 유지: {target['desc']}): ").strip()
    if new_desc:
        target["desc"] = new_desc

    new_badge = input(f"\n5) 상단 배지 문구 (Enter 누르면 현재 유지: {target['badge']}): ").strip()
    if new_badge:
        target["badge"] = new_badge

    save_coupang_curation(content, curation)
    print("\n✅ data.js 에 문법 오류 없이 안전하게 저장되었습니다!")
    print(f"   - 상품명: {target['name']}")
    print(f"   - 가  격: {target['price']}")
    print(f"   - 이동URL: {target['url']}\n")


if __name__ == "__main__":
    main()
