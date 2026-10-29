"""
유치원알리미(e-childschoolinfo.moe.go.kr) 2026년 1차 실제 교육·보육 비용 상세 수집 스크립트
- 대상: 수도권 2,918개 전체 유치원 (서울 706, 경기 1,843, 인천 369)
- 수집 엔드포인트: /kinderMt/kinderEducateAndCost.do (공시항목 4-가-1 교육과정비·방과후과정비, 4-가-2 특성화활동비)
- 출력 캐시: opendata_cache/tuition_20261.json
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "opendata_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
TUITION_CACHE_FILE = os.path.join(CACHE_DIR, "tuition_20261.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def to_int_fee(val):
    if val is None:
        return 0
    s = re.sub(r"[^0-9-]", "", str(val))
    if not s or s == "-":
        return 0
    try:
        return max(0, int(s))
    except ValueError:
        return 0


def parse_cost_html(html):
    tables = re.findall(r"<table[^>]*>.*?</table>", html, re.S)
    res = {
        "edu": {
            "total": [0, 0, 0],
            "baseSub": [0, 0, 0],
            "optSub": [0, 0, 0],
            "tuition": [0, 0, 0],
            "snack": [0, 0, 0],
            "meal": [0, 0, 0],
            "material": [0, 0, 0],
        },
        "after": {
            "total": [0, 0, 0],
            "baseSub": [0, 0, 0],
            "optSub": [0, 0, 0],
            "tuition": [0, 0, 0],
            "snack": [0, 0, 0],
            "meal": [0, 0, 0],
            "material": [0, 0, 0],
        },
        "special": {
            "total": [0, 0, 0],
            "count": 0,
            "programs": [],
        },
    }
    if len(tables) < 3:
        return res

    for t_idx, key in [(0, "edu"), (1, "after")]:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[t_idx], re.S)
        sub_idx = 0
        for r in rows[1:]:
            cells = [
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", r, re.S)
            ]
            if not cells:
                continue
            if cells[0] in ("기본경비", "선택경비") and len(cells) >= 5:
                label = cells[1]
                vals = cells[2:5]
            elif len(cells) >= 4:
                label = cells[0]
                vals = cells[1:4]
            else:
                continue
            v3 = [to_int_fee(x) for x in vals[:3]]
            if len(v3) < 3:
                continue
            if "합계" in label:
                res[key]["total"] = v3
            elif "소계" in label:
                if sub_idx == 0:
                    res[key]["baseSub"] = v3
                else:
                    res[key]["optSub"] = v3
                sub_idx += 1
            elif label == "수업료":
                res[key]["tuition"] = v3
            elif label == "간식비":
                res[key]["snack"] = v3
            elif label == "급식비":
                res[key]["meal"] = v3
            elif "교재" in label:
                res[key]["material"] = v3

    rows2 = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[2], re.S)
    progs = []
    age_idx = -1
    for r in rows2[1:]:
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", r, re.S)
        ]
        if not cells:
            continue
        if cells[0].startswith("만 3세"):
            age_idx = 0
        elif cells[0].startswith("만 4세"):
            age_idx = 1
        elif cells[0].startswith("만 5세"):
            age_idx = 2
        else:
            if len(cells) >= 6:
                p_name = cells[1]
                if p_name and p_name != "-" and "해당사항" not in p_name and p_name not in progs:
                    progs.append(p_name)
            continue

        if len(cells) >= 9:
            cnt = to_int_fee(cells[1])
            if cnt > res["special"]["count"]:
                res["special"]["count"] = cnt
            p_name = cells[3]
            if p_name and p_name != "-" and "해당사항" not in p_name and p_name not in progs:
                progs.append(p_name)
            tot_val = to_int_fee(cells[8])
            if 0 <= age_idx <= 2:
                res["special"]["total"][age_idx] = tot_val

    res["special"]["programs"] = progs[:8]
    return res


def resolve_all_itt_ids(cap_k):
    print("[1/2] 유치원 고유 식별코드(ittId) 매핑 중...")
    url = "https://e-childschoolinfo.moe.go.kr/kinderMt/kinderLocalFind.do"
    data = urllib.parse.urlencode(
        {"institutionType": "01", "latitude": "37.5665", "longitude": "126.9780", "distance": "200"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
    )
    local_list = json.loads(urllib.request.urlopen(req, context=ctx, timeout=25).read().decode("utf-8"))

    by_name_tel = {}
    by_name_addr = {}
    by_name = {}
    for item in local_list:
        nm = (item.get("name") or "").strip()
        tel = re.sub(r"[^0-9]", "", item.get("tel") or "")
        addr = (item.get("roadAddress") or "").strip()
        by_name_tel[(nm, tel)] = item
        by_name_addr[(nm, addr)] = item
        by_name.setdefault(nm, []).append(item)

    id_map = {}
    for k in cap_k:
        kid = k["id"]
        nm = k["name"].strip()
        tel = re.sub(r"[^0-9]", "", k["phone"] or "")
        addr = k["address"].strip()
        hit = by_name_addr.get((nm, addr)) or by_name_tel.get((nm, tel))
        if not hit and nm in by_name and len(by_name[nm]) == 1:
            hit = by_name[nm][0]
        if hit:
            id_map[kid] = hit["id"]
        else:
            # Fallback to combineFindAutoComplete.do
            ac_url = "https://e-childschoolinfo.moe.go.kr/kinderMt/combineFindAutoComplete.do"
            ac_data = urllib.parse.urlencode(
                {"organName": nm, "sidoCode": "99", "sggCode": "99", "roName": "99"}
            ).encode("utf-8")
            ac_req = urllib.request.Request(
                ac_url,
                data=ac_data,
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"},
            )
            ac_res = json.loads(urllib.request.urlopen(ac_req, context=ctx, timeout=15).read().decode("utf-8"))
            cands = [x for x in ac_res if x.get("typeCode") == "01" and x.get("label") == nm]
            chosen = None
            for c in cands:
                r_addr = (c.get("roadAddress") or "").strip()
                if k["sido"] in r_addr and k["sigungu"].split()[0] in r_addr:
                    chosen = c
                    break
            if not chosen and cands:
                chosen = cands[0]
            if chosen:
                id_map[kid] = chosen["id"]

    print(f" -> 매핑 완료: {len(id_map)} / {len(cap_k)}개")
    return id_map


def fetch_one_tuition(kid, itt_id):
    cost_url = "https://e-childschoolinfo.moe.go.kr/kinderMt/kinderEducateAndCost.do"
    data = urllib.parse.urlencode({"ittId": itt_id}).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                cost_url,
                data=data,
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"},
            )
            html = urllib.request.urlopen(req, context=ctx, timeout=20).read().decode("utf-8", errors="ignore")
            parsed = parse_cost_html(html)
            parsed["ittId"] = itt_id
            return kid, parsed
        except Exception as e:
            if attempt == 2:
                return kid, {"ittId": itt_id, "error": str(e)}
            time.sleep(0.5 * (attempt + 1))


def main():
    with open(os.path.join(BASE_DIR, "capital_kindergartens_20261.json"), "r", encoding="utf-8") as f:
        cap_k = json.load(f)

    existing = {}
    if os.path.exists(TUITION_CACHE_FILE):
        try:
            with open(TUITION_CACHE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    id_map = resolve_all_itt_ids(cap_k)

    todo = [(k["id"], id_map[k["id"]]) for k in cap_k if k["id"] in id_map and (k["id"] not in existing or "edu" not in existing[k["id"]])]
    print(f"[2/2] 교육·보육 비용 공시 수집 시작: 신규 {len(todo)}개 (기존 캐시 {len(existing)}개)")

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=25) as ex:
        futures = {ex.submit(fetch_one_tuition, kid, iid): kid for kid, iid in todo}
        for fut in as_completed(futures):
            kid, res = fut.result()
            existing[kid] = res
            done += 1
            if done % 250 == 0 or done == len(todo):
                elapsed = time.time() - t0
                print(f" -> 진행률: {done}/{len(todo)} ({done/len(todo)*100:.1f}%) - 경과 {elapsed:.1f}초")
                with open(TUITION_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False)

    print(f"수집 완료! 총 {len(existing)}개 유치원 비용 캐시 저장됨: {TUITION_CACHE_FILE}")


if __name__ == "__main__":
    main()
