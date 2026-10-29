"""
유치원알리미 Open API 수도권(서울·경기·인천) 공시 데이터 자동 수집 스크립트
- 대상 권역: 서울특별시(11), 인천광역시(28), 경기도(41)
- API 발급처: https://e-childschoolinfo.moe.go.kr/openApi/openApiIntro.do
- 사용법:
  1) 아래 API_KEY 변수에 발급받은 인증키 입력 (또는 환경변수 KINDER_API_KEY 설정)
  2) python fetch_kinder_api.py 실행 -> capital_kindergartens.json 생성
"""

import json
import os
import time
import urllib.parse
import urllib.request

API_KEY = os.environ.get("KINDER_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = "https://e-childschoolinfo.moe.go.kr/api/notice"

# 수도권 3개 시·도 및 주요 시·군·구 행정표준코드 매핑
CAPITAL_REGION_CODES = {
    "서울특별시": {
        "sidoCode": "11",
        "sigungu": {
            "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200",
            "광진구": "11215", "동대문구": "11230", "중랑구": "11260", "성북구": "11290",
            "강북구": "11305", "도봉구": "11320", "노원구": "11350", "은평구": "11380",
            "서대문구": "11410", "마포구": "11440", "양천구": "11470", "강서구": "11500",
            "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
            "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710",
            "강동구": "11740"
        }
    },
    "인천광역시": {
        "sidoCode": "28",
        "sigungu": {
            "중구": "28110", "동구": "28140", "미추홀구": "28177", "연수구": "28185",
            "남동구": "28200", "부평구": "28237", "계양구": "28245", "서구": "28260",
            "강화군": "28710", "옹진군": "28720"
        }
    },
    "경기도": {
        "sidoCode": "41",
        "sigungu": {
            "수원시": "41110", "성남시": "41130", "의정부시": "41150", "안양시": "41170",
            "부천시": "41190", "광명시": "41210", "평택시": "41220", "동두천시": "41250",
            "안산시": "41270", "고양시": "41280", "과천시": "41290", "구리시": "41310",
            "남양주시": "41360", "오산시": "41370", "시흥시": "41390", "군포시": "41410",
            "의왕시": "41430", "하남시": "41450", "용인시": "41460", "파주시": "41480",
            "이천시": "41500", "안성시": "41550", "김포시": "41570", "화성시": "41590",
            "광주시": "41610", "양주시": "41630", "포천시": "41650", "여주시": "41670",
            "연천군": "41800", "가평군": "41820", "양평군": "41830"
        }
    }
}


def fetch_endpoint(endpoint: str, sido_code: str, sgg_code: str) -> list:
    """유치원알리미 특정 엔드포인트(예: basicInfo2.do) 호출"""
    params = urllib.parse.urlencode({
        "key": API_KEY,
        "sidoCode": sido_code,
        "sggCode": sgg_code
    })
    url = f"{BASE_URL}/{endpoint}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("kinderInfo", [])


def normalize_establish_type(raw_est: str) -> str:
    if "단설" in raw_est:
        return "국공립(단설)"
    if "병설" in raw_est or "공립" in raw_est:
        return "국공립(병설)"
    return "사립"


def collect_capital_region():
    if API_KEY == "YOUR_API_KEY_HERE":
        print("[안내] 유치원알리미 Open API 키(KINDER_API_KEY)를 설정한 뒤 실행해 주세요.")
        return

    results = []
    for sido_name, info in CAPITAL_REGION_CODES.items():
        sido_code = info["sidoCode"]
        for sgg_name, sgg_code in info["sigungu"].items():
            print(f"수집 중: {sido_name} {sgg_name} ({sgg_code})...")
            try:
                basics = fetch_endpoint("basicInfo2.do", sido_code, sgg_code)
                buses = {
                    row.get("kinderCode"): row
                    for row in fetch_endpoint("schoolBus2.do", sido_code, sgg_code)
                }
                teachers = {
                    row.get("kinderCode"): row
                    for row in fetch_endpoint("yearOfWork2.do", sido_code, sgg_code)
                }
            except Exception as err:
                print(f"  [경고] {sido_name} {sgg_name} 호출 실패: {err}")
                continue

            for b in basics:
                kcode = b.get("kinderCode")
                bus = buses.get(kcode, {})
                tch = teachers.get(kcode, {})

                cap3 = int(b.get("ag3fpcnt") or 0)
                cap4 = int(b.get("ag4fpcnt") or 0)
                cap5 = int(b.get("ag5fpcnt") or 0)
                enr3 = int(b.get("ag3ppcnt") or 0)
                enr4 = int(b.get("ag4ppcnt") or 0)
                enr5 = int(b.get("ag5ppcnt") or 0)

                over4 = int(tch.get("yy4_6_abv") or 0) + int(tch.get("yy6_abv") or 0)
                total_tch = max(1, int(tch.get("total") or 10))
                has_bus = str(bus.get("vhcl_oprn_yn", "N")).upper() == "Y"
                bus_cnt = int(bus.get("opra_vhcnt") or 0)

                results.append({
                    "id": kcode or f"kg-{len(results)+1}",
                    "name": b.get("kindername", ""),
                    "establishType": normalize_establish_type(b.get("establish", "")),
                    "sido": sido_name,
                    "sigungu": sgg_name,
                    "dong": b.get("dong", sgg_name),
                    "address": b.get("addr", ""),
                    "phone": b.get("telno", ""),
                    "homepage": b.get("hpaddr") or "https://e-childschoolinfo.moe.go.kr",
                    "establishedYear": int(str(b.get("edate", "2018"))[:4] or 2018),
                    "capacityTotal": cap3 + cap4 + cap5,
                    "enrolledTotal": enr3 + enr4 + enr5,
                    "teachers": {
                        "total": total_tch,
                        "regularTeacher": max(1, total_tch - 2),
                        "over4yr": over4
                    },
                    "operation": {
                        "eduTime": b.get("opertime", "09:00 ~ 14:00"),
                        "afterSchoolTime": "14:00 ~ 19:30",
                        "afterSchoolEndHour": 19.5,
                        "hasBus": has_bus,
                        "busCount": bus_cnt
                    }
                })
            time.sleep(0.25)

    out_path = os.path.join(os.path.dirname(__file__), "capital_kindergartens.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"수집 완료: 총 {len(results)}개 수도권 유치원 저장 -> {out_path}")


if __name__ == "__main__":
    collect_capital_region()
