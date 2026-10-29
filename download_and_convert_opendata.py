"""
유치원알리미 공시자료 다운로드(openData.do) 무인증 직접 수집 및 앱 데이터(data.js) 변환 스크립트
- 대상 지역: 수도권 (서울특별시 11, 인천광역시 28, 경기도 41)
- 대상 공시차수: 2026년 1차 (20261)
- 수집 및 병합 항목 (총 11개 핵심 공시항목):
  [05] 일반 현황 (설립유형, 주소, 전화, 홈페이지, 운영시간, 연령별 학급·정원·현원, 위경도)
  [06] 직위·자격별 교직원 현황 (원장, 원감, 수석·보직·일반·특수·보건·영양·기간제교원, 자격증 현황)
  [07] 교사의 현 기관 근속연수 (1년 미만 ~ 6년 이상 구간별 교사 수)
  [041] 교실면적 현황 (교실수, 교실면적, 실내체육장, 보건/위생, 조리/급식공간)
  [042] 건물 현황 (건축년도, 건물층수, 건물전용면적, 대지총면적)
  [10] 수업일수 현황 (만3·4·5세 수업일수, 방과후과정 수업일수)
  [111] 방과후 과정 편성·운영 현황 (방과후 시작·종료시간, 방과후 학급수, 참여원아수, 전담인력)
  [14] 급식실시 현황 (직영/위탁 구분, 급식유아수, 영양교사 배치여부, 조리사/조리인력수)
  [15] 환경위생관리 현황 (실내공기질, 정기소독, 음용수 종류, 미세먼지, 조도관리 점검결과)
  [19] 통학차량 현황 (차량운영여부, 운행차량수, 신고차량수, 9/12/15인승 대수)
  [22] 안전점검 현황 (소방대피훈련, 가스·소방·전기·놀이시설 점검결과, 실내외 CCTV 설치 대수)
"""

import urllib.request
import urllib.parse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "opendata_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

REGIONS = [
    ("11", "서울특별시"),
    ("41", "경기도"),
    ("28", "인천광역시"),
]

CODES = ["05", "06", "07", "041", "042", "10", "111", "14", "15", "19", "22"]
TIMING = "20261"


def fetch_item(sido_code, sido_name, gongsi_code):
    cache_file = os.path.join(CACHE_DIR, f"{TIMING}_{sido_code}_{gongsi_code}.json")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    enc_name = urllib.parse.quote(sido_name)
    url = (
        f"https://e-childschoolinfo.moe.go.kr/download/getOpenData.do"
        f"?combineSidoCode={sido_code}&combineSidoName={enc_name}"
        f"&timingListCode={TIMING}&gongsiListCode={gongsi_code}&ExcelCsv=3"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://e-childschoolinfo.moe.go.kr/openData.do",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def to_int(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val)
    s = re.sub(r"[^0-9-]", "", str(val))
    if not s or s == "-":
        return default
    try:
        return int(s)
    except ValueError:
        return default


def to_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^0-9.-]", "", str(val))
    if not s or s in ("-", "."):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def parse_hm(s):
    """'08시 40분' 또는 '0840시0840분' 형태를 ('08:40', 8.67) 로 변환"""
    s = str(s or "").strip()
    m = re.search(r"(\d{1,4})시\s*(\d{1,4})분", s)
    if not m:
        return "", 0.0
    h_raw, mi_raw = m.group(1), m.group(2)
    if len(h_raw) >= 3:
        s4 = h_raw.zfill(4)
        h, mi = int(s4[:2]), int(s4[2:4])
    else:
        h, mi = int(h_raw), int(mi_raw)
    if h < 0 or h > 24 or mi < 0 or mi >= 60:
        return "", 0.0
    return f"{h:02d}:{mi:02d}", round(h + mi / 60.0, 2)


def parse_operating_range(op_str):
    """'0800시0800분~1900시1900분' -> ('08:00', '19:00', 19.0)"""
    op_str = str(op_str or "")
    if "~" not in op_str:
        return "09:00", "18:00", 18.0
    left, right = op_str.split("~", 1)
    st, _ = parse_hm(left)
    et, eh = parse_hm(right)
    return (st or "09:00"), (et or "18:00"), (eh or 18.0)


def parse_address(sido_name, addr):
    addr = (addr or "").strip()
    tokens = addr.split()
    sigungu = "기타"
    if len(tokens) >= 2:
        t1 = tokens[1]
        if sido_name == "경기도" and len(tokens) >= 3 and tokens[2].endswith("구") and len(tokens[2]) <= 4:
            sigungu = f"{t1} {tokens[2]}"
        else:
            sigungu = t1

    dong = ""
    # 1. 괄호 안 법정동 추출: 예) (청라동), (마전동, 동아아파트)
    m = re.findall(r"\(([^)]+)\)", addr)
    for grp in reversed(m):
        parts = [p.strip() for p in grp.split(",")]
        for p in parts:
            p_tok = p.split()[0] if p else ""
            if re.search(r"(동|읍|면|가|리)$", p_tok) and not p_tok.endswith("로") and not p_tok.endswith("길"):
                dong = p_tok
                break
        if dong:
            break

    # 2. 괄호 밖 토큰에서 읍/면/동 추출
    if not dong:
        for tok in tokens[2:]:
            clean_tok = re.sub(r"[(),]", "", tok)
            if re.search(r"(읍|면|동|가)$", clean_tok) and not clean_tok.endswith("로") and not clean_tok.endswith("길"):
                dong = clean_tok
                break

    # 3. 도로명 주소만 있는 경우 메인 도로명(OO로 / OO대로 / OO길)으로 정규화
    if not dong:
        for tok in tokens[2:]:
            clean_tok = re.sub(r"[(),]", "", tok)
            m_road = re.match(r"^([가-힣0-9]+?(?:대로|로))(?:\d+.*)?$", clean_tok)
            if m_road:
                dong = m_road.group(1)
                break
            m_gil = re.match(r"^([가-힣]+?길)(?:\d+.*)?$", clean_tok)
            if m_gil:
                dong = m_gil.group(1)
                break

    if not dong:
        dong = "기타"

    return sigungu, dong


def normalize_establish_type(raw_type):
    raw_type = str(raw_type or "").strip()
    if "단설" in raw_type or raw_type == "국립":
        return "국공립(단설)"
    if "병설" in raw_type or "공립" in raw_type:
        return "국공립(병설)"
    if "법인" in raw_type:
        return "사립(법인)"
    return "사립(사인)"


def build_dataset():
    all_records = []
    tuition_cache_path = os.path.join(CACHE_DIR, "tuition_20261.json")
    tuition_map = {}
    if os.path.exists(tuition_cache_path):
        with open(tuition_cache_path, "r", encoding="utf-8") as f:
            tuition_map = json.load(f)

    for scode, sname in REGIONS:
        tables = {}
        for gcode in CODES:
            tables[gcode] = fetch_item(scode, sname, gcode)["body"]

        # 보조 테이블을 (유치원명, 주소) 키로 인덱싱 (1:1 순서 일치 + 안전 매칭)
        idx_tables = {}
        for gcode in CODES[1:]:
            mapping = {}
            for row in tables[gcode]:
                key = (str(row[2]).strip(), str(row[4]).strip())
                mapping[key] = row
            idx_tables[gcode] = mapping

        rows_05 = tables["05"]
        for i, r05 in enumerate(rows_05):
            k_name = str(r05[2]).strip()
            k_addr = str(r05[8]).strip()
            key = (k_name, k_addr)

            r06 = idx_tables["06"].get(key) or (tables["06"][i] if i < len(tables["06"]) else [])
            r07 = idx_tables["07"].get(key) or (tables["07"][i] if i < len(tables["07"]) else [])
            r041 = idx_tables["041"].get(key) or (tables["041"][i] if i < len(tables["041"]) else [])
            r042 = idx_tables["042"].get(key) or (tables["042"][i] if i < len(tables["042"]) else [])
            r10 = idx_tables["10"].get(key) or (tables["10"][i] if i < len(tables["10"]) else [])
            r111 = idx_tables["111"].get(key) or (tables["111"][i] if i < len(tables["111"]) else [])
            r14 = idx_tables["14"].get(key) or (tables["14"][i] if i < len(tables["14"]) else [])
            r15 = idx_tables["15"].get(key) or (tables["15"][i] if i < len(tables["15"]) else [])
            r19 = idx_tables["19"].get(key) or (tables["19"][i] if i < len(tables["19"]) else [])
            r22 = idx_tables["22"].get(key) or (tables["22"][i] if i < len(tables["22"]) else [])

            est_type = normalize_establish_type(r05[3])
            is_public = est_type.startswith("국공립")
            is_danseol = "단설" in est_type

            sigungu, dong = parse_address(sname, k_addr)
            open_date = str(r05[7] or r05[6] or "20150301").strip()
            est_year = to_int(open_date[:4], 2015)
            if est_year < 1900 or est_year > 2026:
                est_year = 2015

            phone = str(r05[9] or "").strip()
            homepage = str(r05[11] or "").strip()
            if not homepage or homepage == "-":
                homepage = "https://e-childschoolinfo.moe.go.kr"

            # 학급 및 원아 수 (05)
            c3_cnt, c4_cnt, c5_cnt, cm_cnt, cs_cnt = (
                to_int(r05[13]),
                to_int(r05[14]),
                to_int(r05[15]),
                to_int(r05[16]),
                to_int(r05[17]),
            )
            cap_total = to_int(r05[18])
            c3_cap, c4_cap, c5_cap, cm_cap, cs_cap = (
                to_int(r05[19]),
                to_int(r05[20]),
                to_int(r05[21]),
                to_int(r05[22]),
                to_int(r05[23]),
            )
            c3_enr, c4_enr, c5_enr, cm_enr, cs_enr = (
                to_int(r05[24]),
                to_int(r05[25]),
                to_int(r05[26]),
                to_int(r05[27]),
                to_int(r05[28]),
            )
            enr_total = c3_enr + c4_enr + c5_enr + cm_enr + cs_enr
            if cap_total <= 0:
                cap_total = max(c3_cap + c4_cap + c5_cap + cm_cap + cs_cap, enr_total, 1)

            lat = to_float(r05[29], 0.0)
            lng = to_float(r05[30], 0.0)

            # 교직원 현황 (06) & 근속연수 (07)
            # 06: 5원장, 6원감, 7수석, 8보직, 9일반, 10특수, 11보건, 12영양, 13기간제/강사, 14직원, 15수석자격, 16정교사1급, 17정교사2급
            t_principal = to_int(r06[5]) if len(r06) > 5 else 0
            t_vice = to_int(r06[6]) if len(r06) > 6 else 0
            t_head = to_int(r06[7]) if len(r06) > 7 else 0
            t_bojik = to_int(r06[8]) if len(r06) > 8 else 0
            t_general = to_int(r06[9]) if len(r06) > 9 else 0
            t_special = to_int(r06[10]) if len(r06) > 10 else 0
            t_health = to_int(r06[11]) if len(r06) > 11 else 0
            t_nutri = to_int(r06[12]) if len(r06) > 12 else 0
            t_temp = to_int(r06[13]) if len(r06) > 13 else 0
            t_cert1 = to_int(r06[16]) if len(r06) > 16 else 0

            # 담임/수업 담당 교원 수 (수석+보직+일반+특수교사, 만약 0이면 기간제 포함)
            regular_teachers = t_head + t_bojik + t_general + t_special
            if regular_teachers <= 0:
                regular_teachers = max(t_head + t_bojik + t_general + t_special + t_temp, c3_cnt + c4_cnt + c5_cnt + cm_cnt + cs_cnt, 1)

            # 근속연수 (07): 5(1년미만), 6(1~2년), 7(2~4년), 8(4~6년), 9(6년이상)
            ten_u1 = to_int(r07[5]) if len(r07) > 5 else 0
            ten_1to2 = to_int(r07[6]) if len(r07) > 6 else 0
            ten_2to4 = to_int(r07[7]) if len(r07) > 7 else 0
            ten_4to6 = to_int(r07[8]) if len(r07) > 8 else 0
            ten_over6 = to_int(r07[9]) if len(r07) > 9 else 0

            under2yr = ten_u1 + ten_1to2
            yr2to4 = ten_2to4
            over4yr = ten_4to6 + ten_over6
            tenure_total = under2yr + yr2to4 + over4yr
            if tenure_total <= 0:
                tenure_total = max(regular_teachers, 1)

            # 운영시간 및 방과후 과정 (05, 111, 10)
            op_st, op_et, op_eh = parse_operating_range(r05[12])
            af_st, _ = parse_hm(r111[5]) if len(r111) > 5 else ("", 0.0)
            af_et, af_eh = parse_hm(r111[6]) if len(r111) > 6 else ("", 0.0)

            start_time = af_st or op_st or "08:30"
            end_time = af_et or op_et or "19:00"
            end_hour = af_eh if af_eh > 0 else op_eh

            af_classes = to_int(r111[9]) if len(r111) > 9 else 0
            af_enrolled = to_int(r111[12]) if len(r111) > 12 else 0
            af_staff = to_int(r111[18]) if len(r111) > 18 else 0

            # 수업일수 (10): 5(만3세), 6(만4세), 7(만5세), 10(방과후과정수업일수)
            edu_days = max(
                to_int(r10[5]) if len(r10) > 5 else 0,
                to_int(r10[6]) if len(r10) > 6 else 0,
                to_int(r10[7]) if len(r10) > 7 else 0,
                180,
            )
            af_days = to_int(r10[10]) if len(r10) > 10 else 0

            edu_time_str = f"{start_time} ~ 14:00 (수업일수 {edu_days}일)"
            after_time_str = f"{start_time} ~ {end_time}"
            if af_days >= 220:
                vac_care = f"방학 중 돌봄 상시 운영 (방과후 연간 {af_days}일 · 참여 {af_enrolled}명)"
            elif af_days > 0:
                vac_care = f"방과후 과정 연간 {af_days}일 운영 (참여 {af_enrolled}명)"
            else:
                vac_care = f"방과후 돌봄 {af_classes}학급 운영 (참여 {af_enrolled}명)"

            # 통학차량 (19): 5(차량운영여부), 6(운행차량수)
            bus_yn = str(r19[5] or "").strip() if len(r19) > 5 else ""
            bus_cnt = to_int(r19[6]) if len(r19) > 6 else 0
            has_bus = (bus_yn == "운영" and bus_cnt > 0) or bus_cnt > 0

            # 급식실시 (14): 5(급식운영방식구분), 9(영양교사배치여부), 13(조리사수), 14(조리인력수)
            meal_mode = str(r14[5] or "직영").strip() if len(r14) > 5 else "직영"
            nutri_yn = str(r14[9] or "").strip() if len(r14) > 9 else ""
            cook_cnt = (to_int(r14[13]) if len(r14) > 13 else 0) + (to_int(r14[14]) if len(r14) > 14 else 0)
            meal_parts = [f"{meal_mode}급식" if not meal_mode.endswith("급식") else meal_mode]
            if nutri_yn == "O":
                meal_parts.append("영양교사 배치")
            if cook_cnt > 0:
                meal_parts.append(f"조리인력 {cook_cnt}명")
            meal_type_str = " · ".join(meal_parts)

            # 교실면적 (041) & 건물현황 (042)
            # 041: 5(교실수), 6(교실면적), 7(실내체육장)
            # 042: 5(건축년도), 6(건물층수), 7(건물전용면적), 8(대지총면적)
            classroom_area = to_int(r041[6]) if len(r041) > 6 else 0
            indoor_gym = to_int(r041[7]) if len(r041) > 7 else 0
            building_area = to_int(r042[7]) if len(r042) > 7 else 0
            land_area = to_int(r042[8]) if len(r042) > 8 else 0
            denom = enr_total if enr_total > 0 else cap_total
            per_child_area = round(classroom_area / max(denom, 1), 1)

            # 안전점검 (22) & 환경위생 (15)
            # 22: 17(CCTV 안), 18(CCTV 밖), 19(CCTV 총)
            cctv_in = to_int(r22[17]) if len(r22) > 17 else 0
            cctv_out = to_int(r22[18]) if len(r22) > 18 else 0
            cctv_total = to_int(r22[19]) if len(r22) > 19 else (cctv_in + cctv_out)
            air_res = str(r15[6] or "적합").strip() if len(r15) > 6 else "적합"
            play_res = str(r22[15] or "합격").strip() if len(r22) > 15 else "합격"
            safety_ok = (air_res in ("적합", "실시", "-")) and (play_res in ("합격", "적합", "-"))

            # 유치원알리미 2026년 1차 실제 교육·보육 비용 공시 데이터(tuition_20261.json) 반영
            kid = f"kg-{scode}-{i+1:04d}"
            t_info = tuition_map.get(kid, {})
            itt_id = t_info.get("ittId", "")
            edu_d = t_info.get("edu", {})
            after_d = t_info.get("after", {})
            spec_d = t_info.get("special", {})

            edu_tot = edu_d.get("total", [0, 0, 0])
            edu_base = edu_d.get("baseSub", [0, 0, 0])
            edu_opt = edu_d.get("optSub", [0, 0, 0])
            edu_tui = edu_d.get("tuition", [0, 0, 0])
            edu_meal = edu_d.get("meal", [0, 0, 0])
            edu_snack = edu_d.get("snack", [0, 0, 0])

            after_tot = after_d.get("total", [0, 0, 0])
            after_base = after_d.get("baseSub", [0, 0, 0])
            after_opt = after_d.get("optSub", [0, 0, 0])
            after_tui = after_d.get("tuition", [0, 0, 0])
            after_meal = after_d.get("meal", [0, 0, 0])
            after_snack = after_d.get("snack", [0, 0, 0])

            spec_tot = spec_d.get("total", [0, 0, 0])
            spec_cnt = to_int(spec_d.get("count", 0))
            spec_progs = [str(p).strip() for p in spec_d.get("programs", []) if str(p).strip()]

            age_totals = [edu_tot[a] + after_tot[a] + spec_tot[a] for a in range(3)]
            active_ages = [
                a
                for a, (cnt, cap, enr, tot) in enumerate(
                    [
                        (c3_cnt, c3_cap, c3_enr, age_totals[0]),
                        (c4_cnt, c4_cap, c4_enr, age_totals[1]),
                        (c5_cnt, c5_cap, c5_enr, age_totals[2]),
                    ]
                )
                if cnt > 0 or cap > 0 or enr > 0 or tot > 0
            ]
            if not active_ages:
                active_ages = [0, 1, 2]

            avg_edu = round(sum(edu_tot[a] for a in active_ages) / len(active_ages))
            avg_edu_base = round(sum(edu_base[a] for a in active_ages) / len(active_ages))
            avg_edu_opt = round(sum(edu_opt[a] for a in active_ages) / len(active_ages))
            avg_after = round(sum(after_tot[a] for a in active_ages) / len(active_ages))
            avg_spec = round(sum(spec_tot[a] for a in active_ages) / len(active_ages))
            avg_meal = round(
                sum(edu_meal[a] + edu_snack[a] + after_meal[a] + after_snack[a] for a in active_ages)
                / len(active_ages)
            )
            monthly_total = round(sum(age_totals[a] for a in active_ages) / len(active_ages))

            if age_totals[0] == age_totals[1] == age_totals[2]:
                age_note = f"만3·4·5세 동일 월 {age_totals[0]:,}원"
            else:
                age_note = f"만3세 {age_totals[0]:,}원 · 만4세 {age_totals[1]:,}원 · 만5세 {age_totals[2]:,}원"

            if spec_progs:
                note_str = f"2026년 1차 알리미 실공시 ({age_note} | 특성화: {', '.join(spec_progs[:4])})"
            else:
                note_str = f"2026년 1차 알리미 실공시 ({age_note} · 교육과정+방과후+특성화 합산)"

            cost_obj = {
                "monthlyTotal": monthly_total,
                "tuition": avg_edu,
                "eduBase": avg_edu_base,
                "eduOpt": avg_edu_opt,
                "afterSchoolFee": avg_after,
                "specialActivityFee": avg_spec,
                "mealFee": avg_meal,
                "byAge": {
                    "total": age_totals,
                    "edu": edu_tot,
                    "eduBase": edu_base,
                    "eduOpt": edu_opt,
                    "after": after_tot,
                    "special": spec_tot,
                },
                "specialCount": spec_cnt,
                "specialPrograms": spec_progs,
                "note": note_str,
            }

            # 공시 데이터 기반 실제 강점 태그 & 특색 배지 자동 생성
            special_programs = []
            tags = ["국공립" if is_public else "사립"]
            if is_danseol:
                tags.append("단설")
                special_programs.append("단독건물 국공립")
            elif is_public:
                tags.append("병설")

            if spec_progs:
                for sp in spec_progs[:2]:
                    special_programs.append(f"특성화:{sp}")
            if cs_cnt > 0:
                special_programs.append(f"특수학급({cs_cnt}학급)")
                tags.append("특수학급")
            if cm_cnt > 0:
                special_programs.append(f"혼합연령({cm_cnt}학급)")
            if indoor_gym > 0:
                special_programs.append(f"실내체육장({indoor_gym}㎡)")
                tags.append("실내체육장")
            if has_bus:
                tags.append("통학버스")
            if end_hour >= 19.0:
                tags.append("저녁돌봄")
            if af_days >= 230:
                special_programs.append(f"연중돌봄({af_days}일)")
            if nutri_yn == "O":
                special_programs.append("영양교사 배치")
            if t_cert1 >= 3:
                special_programs.append(f"1급정교사 {t_cert1}명")

            alimi_url = (
                f"https://e-childschoolinfo.moe.go.kr/kinderMt/kinderSummary.do?ittId={itt_id}"
                if itt_id
                else "https://e-childschoolinfo.moe.go.kr"
            )
            if not homepage or homepage == "-" or "e-childschoolinfo.moe.go.kr" in homepage:
                homepage = alimi_url

            rec = {
                "id": kid,
                "ittId": itt_id,
                "name": k_name,
                "establishType": est_type,
                "eduOffice": str(r05[1] or "").strip(),
                "sido": sname,
                "sigungu": sigungu,
                "dong": dong,
                "address": k_addr,
                "phone": phone,
                "homepage": homepage,
                "establishedYear": est_year,
                "lat": lat,
                "lng": lng,
                "classes": {
                    "age3": {"count": c3_cnt, "capacity": c3_cap, "enrolled": c3_enr},
                    "age4": {"count": c4_cnt, "capacity": c4_cap, "enrolled": c4_enr},
                    "age5": {"count": c5_cnt, "capacity": c5_cap, "enrolled": c5_enr},
                    "mixed": {"count": cm_cnt, "capacity": cm_cap, "enrolled": cm_enr},
                    "special": {"count": cs_cnt, "capacity": cs_cap, "enrolled": cs_enr},
                },
                "capacityTotal": cap_total,
                "enrolledTotal": enr_total,
                "teachers": {
                    "total": tenure_total,
                    "regularTeacher": regular_teachers,
                    "over4yr": over4yr,
                    "yr2to4": yr2to4,
                    "under2yr": under2yr,
                    "tier1Cert": t_cert1,
                    "specialTeacher": t_special,
                    "healthTeacher": t_health,
                    "nutritionTeacher": t_nutri,
                },
                "cost": cost_obj,
                "operation": {
                    "eduTime": edu_time_str,
                    "afterSchoolTime": after_time_str,
                    "afterSchoolEndHour": end_hour,
                    "afterSchoolEnrolled": af_enrolled,
                    "afterSchoolDays": af_days,
                    "eduDays": edu_days,
                    "vacationCare": vac_care,
                    "hasBus": has_bus,
                    "busCount": bus_cnt,
                    "mealType": meal_type_str,
                },
                "facilitySafety": {
                    "classroomAreaSqm": classroom_area,
                    "perChildAreaSqm": per_child_area,
                    "indoorGymSqm": indoor_gym,
                    "outdoorPlaygroundSqm": land_area,
                    "buildingAreaSqm": building_area,
                    "cctvTotal": cctv_total,
                    "cctvIndoor": cctv_in,
                    "cctvOutdoor": cctv_out,
                    "safetyAllPassed": safety_ok,
                },
                "specialPrograms": special_programs[:4],
                "tags": tags,
            }
            all_records.append(rec)

    return all_records


COUPANG_CURATION = {
    "disclaimer": "이 배너는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.",
    "inFeedBanner": {
        "badge": "🎒 3월 첫 등원 필수템 체크리스트",
        "title": "유치원 입학 전 선배 엄마들이 가장 먼저 품절 전에 쟁이는 준비물 4가지",
        "subtitle": "단체생활 첫걸음, 선생님도 편하고 아이도 좋아하는 베스트셀러만 모았어요",
    },
    "items": [
        {
            "id": "cp-1",
            "category": "등원필수",
            "badge": "선배맘 1위",
            "name": "MS 붙이는 신개념 이름만 올록볼록 네임스티커 방수 어린이집 이름표 스티커",
            "desc": "물병·식판·칫솔·학용품 어디든 글자만 깔끔하게 붙는 방수 이름표",
            "price": "6,700원",
            "rating": "4.9 (후기 4,820+)",
            "emoji": "🏷️",
            "image": "https://thumbnail9.coupangcdn.com/thumbnails/remote/212x212ex/image/vendor_inventory/717d/d081764de1de629f274778a5c08e6c2e4ee679ff756a48bd6a8e778470b6.jpg",
            "url": "https://link.coupang.com/re/AFFSDP?lptag=AF9401277&pageKey=8805712240&itemId=25645706698&traceid=V0-201-b31b23e19bc55155",
        },
        {
            "id": "cp-2",
            "category": "등원필수",
            "badge": "재구매율 1위",
            "name": "베이지버니 자체제작 1+1 이름 파츠 영어 실내화 운동화 이름표 입학준비물",
            "desc": "실내화·운동화 구멍에 쏙 끼우는 우리 아이 맞춤 이니셜 네임파츠",
            "price": "8,900원",
            "rating": "4.9 (후기 9,150+)",
            "emoji": "🏷️",
            "image": "https://thumbnail4.coupangcdn.com/thumbnails/remote/212x212ex/image/vendor_inventory/c4fc/d8bfaeeb266b0a95ccee211045b9eddf56083edda1b4d14c5c848881d159.jpg",
            "url": "https://link.coupang.com/re/AFFSDP?lptag=AF9401277&pageKey=9587751157&itemId=28620708063&traceid=V0-201-c1568d32f1893dee",
        },
        {
            "id": "cp-3",
            "category": "위생·식기",
            "badge": "로켓배송",
            "name": "릴팡 더보틀 원터치 어깨끈 트라이탄 물통, 마이멜로디, 470ml",
            "desc": "가방 속에서 절대 새지 않는 원터치 잠금 구조, 가벼운 어깨끈 포함",
            "price": "12,680원",
            "rating": "4.8 (후기 6,340+)",
            "emoji": "🍱",
            "image": "https://thumbnail4.coupangcdn.com/thumbnails/remote/212x212ex/image/retail/images/62243315087403-9db88231-7de6-4fda-90b7-bafeb976c1b1.jpg",
            "url": "https://link.coupang.com/re/AFFSDP?lptag=AF9401277&pageKey=9080388415&itemId=25914333460&traceid=V0-201-a4dcf7d3d8712877",
        },
        {
            "id": "cp-4",
            "category": "실내화·가방",
            "badge": "발편한 설계",
            "name": "슈라모드 포켓몬스터 셀로 EVA 실내화",
            "desc": "미끄럼 방지 EVA 소재 + 아이 스스로 신고 벗기 편한 초경량 실내화",
            "price": "8,900원",
            "rating": "4.8 (후기 5,110+)",
            "emoji": "👟",
            "image": "https://thumbnail1.coupangcdn.com/thumbnails/remote/212x212ex/image/vendor_inventory/f26c/fcfd91e1eb349590b37ef1334b5ef0b0441bd41920b5162fdd2de55d3c6c.jpg",
            "url": "https://link.coupang.com/re/AFFSDP?lptag=AF9401277&pageKey=6900208519&itemId=16592996238&traceid=V0-201-f0caff80f99678ec",
        },
    ],
}

ADMISSION_GUIDE_DATA = {
    "timeline": [
        {
            "step": "1단계",
            "period": "10월 말",
            "title": "모집요강 공고 & 설명회 참석",
            "desc": "유치원알리미 공시 확인 및 관심 유치원 3~4곳 설명회 예약·방문",
            "active": True,
        },
        {
            "step": "2단계",
            "period": "11월 초",
            "title": "우선모집 원서접수·추첨",
            "desc": "법정저소득층·보훈·다자녀·재원생 형제자매 등 우선자격 1~3지망 접수",
        },
        {
            "step": "3단계",
            "period": "11월 중순",
            "title": "일반모집 원서접수·추첨",
            "desc": "유보통합포털(구 처음학교로)에서 최대 3곳 지망 접수 (중복선발 제한)",
        },
        {
            "step": "4단계",
            "period": "12월 ~ 2월",
            "title": "대기자 순번 이동 & 추가모집",
            "desc": "12월 말까지 대기순번 자동 승격, 결원 발생 유치원 상시 추가모집",
        },
    ],
    "checklists": [
        {
            "title": "📌 유치원 설명회에서 꼭 물어봐야 할 7가지 핵심 질문",
            "items": [
                "1. 방과후(돌봄) 과정이 실제로 몇 시까지 운영되며, 맞벌이 증빙 시 100% 입반 가능한가요?",
                "2. 여름·겨울 방학 기간은 며칠이며, 방학 중 돌봄 시 급식이 정상 제공되나요(도시락 지참 여부)?",
                "3. 통학차량이 우리 단지 앞에 몇 시쯤 정차하며, 아이가 차에 타는 총 시간은 몇 분인가요?",
                "4. 공시된 원비 외에 입학준비금, 현장학습비, 방학특강비 등 연중 추가 실비는 얼마인가요?",
                "5. 한 학급당 정원과 담임교사 외에 보조교사나 부담임 선생님이 어떻게 배치되나요?",
                "6. 하루 일과 중 바깥놀이(실외놀이터/숲활동) 시간은 주 몇 회, 몇 분 정도 확보되나요?",
                "7. 3월 신입생 초기 적응 기간(단축수업)은 며칠 동안 어떻게 진행되나요?",
            ],
        },
        {
            "title": "⚖️ 국공립(단설·병설) vs 사립유치원 한눈에 비교",
            "items": [
                "• 국공립 단설: 유치원 단독 건물로 시설이 크고 연령별 학급이 많으며, 월 부담금이 거의 없음 (경쟁률 높음)",
                "• 국공립 병설: 초등학교 내 위치해 초등 적응에 유리하고 소규모 케어가 강점이나, 통학버스가 없는 곳이 많음",
                "• 사립 유치원: 원어민 영어·몬테소리·숲·체육 등 다양한 특성화 수업과 촘촘한 셔틀버스·방학돌봄이 강점",
            ],
        },
    ],
}

if __name__ == "__main__":
    records = build_dataset()
    json_out = os.path.join(BASE_DIR, "capital_kindergartens_20261.json")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    js_out = os.path.join(BASE_DIR, "data.js")
    with open(js_out, "w", encoding="utf-8") as f:
        f.write("/**\n")
        f.write(" * 유치원알리미 공시자료 다운로드(openData.do) 기반 수도권(서울·경기·인천) 전체 유치원 실데이터셋\n")
        f.write(" * 공시차수: 2026년 1차 (20261) | 총 2,918개 유치원, 11개 공시항목 통합\n")
        f.write(" */\n\n")
        f.write("const KINDERGARTEN_DATA = ")
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const COUPANG_CURATION = ")
        json.dump(COUPANG_CURATION, f, ensure_ascii=False, indent=2)
        f.write(";\n\n")
        f.write("const ADMISSION_GUIDE_DATA = ")
        json.dump(ADMISSION_GUIDE_DATA, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    by_sido = {}
    for r in records:
        by_sido[r["sido"]] = by_sido.get(r["sido"], 0) + 1
    print(f"SUCCESS: Generated {len(records)} kindergartens -> {by_sido}")
    print(f"Saved: {json_out} and {js_out}")
