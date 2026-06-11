import os
import math
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from typing import Dict, Tuple

# =========================================================
# 기본 설정
# =========================================================
load_dotenv()

st.set_page_config(
    page_title="HAEAHN PCM Datacenter Solution",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =========================================================
# API KEY
# =========================================================
LAND_REGULATION_API_KEY = os.getenv("LAND_REGULATION_API_KEY", "")
BUILDING_API_KEY = os.getenv("BUILDING_API_KEY", "")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")

# =========================================================
# API URL
# =========================================================
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
BUILDING_API_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
LAND_REGULATION_URL = "http://apis.data.go.kr/B090026/LandUseService/getInfo"

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {
    margin: 0 !important;
    padding: 0 !important;
    background: #ffffff !important;
}

header, footer, #MainMenu {
    visibility: hidden !important;
    height: 0 !important;
}

[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
    display: none !important;
    height: 0 !important;
}

.block-container {
    padding-top: 0 !important;
    padding-bottom: 0.5rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
    max-width: 100% !important;
}

[data-testid="column"] {
    padding-top: 0 !important;
}

.left-panel {
    border-right: 1px solid #d9d9d9;
    padding-right: 12px;
    min-height: 94vh;
}

.right-panel {
    padding-left: 12px;
    min-height: 94vh;
}

.logo-box {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

.app-title {
    font-size: 1.95rem;
    line-height: 1.08;
    font-weight: 800;
    color: #0B3B82;
    margin-top: 0 !important;
    margin-bottom: 0.35rem !important;
    white-space: nowrap !important;
    overflow: hidden;
    text-overflow: clip;
}

.section-title {
    font-size: 1.02rem;
    font-weight: 700;
    margin-top: 0.75rem;
    margin-bottom: 0.35rem;
}

.stTabs [data-baseweb="tab-list"] {
    margin-top: 0 !important;
    gap: 6px;
}

.stTabs [data-baseweb="tab"] {
    height: 40px;
    padding-left: 14px;
    padding-right: 14px;
}
/* 상단 여백 및 수직 정렬 수정 */
html, body, .stApp, [data-testid="stAppViewContainer"], main, .block-container {
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
    align-items: stretch !important;
    min-height: 100vh !important;
    gap: 0 !important;
}

.block-container {
    padding-top: 0 !important;
}

.left-panel, .right-panel {
    min-height: auto !important;
}
/* left panel primary button styling */
/* stronger override for left-panel primary button */
.left-panel div.stButton > button, .left-panel .stButton>button, .left-panel button, .left-panel button[type="button"] {
    background: #626d7c !important;
    background-image: none !important;
    color: #ffffff !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    padding-top: 0.28rem !important;
    padding-bottom: 0.28rem !important;
    padding-left: 0.6rem !important;
    padding-right: 0.6rem !important;
    font-weight: 600 !important;
    height: auto !important;
    line-height: 1.1 !important;
    box-shadow: none !important;
    border-radius: 6px !important;
}

.left-panel div.stButton > button:hover, .left-panel .stButton>button:hover, .left-panel button:hover {
   filter: brightness(0.95) !important;
}

/* reduce default button thickness overall */
.stButton>button, button[data-baseweb="button"] {
    padding-top: 0.35rem !important;
    padding-bottom: 0.35rem !important;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 포맷 함수
# =========================================================
def fmt_number(value, digits=1):
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except Exception:
        return str(value)

def fmt_area(value): return f"{fmt_number(value, 1)} ㎡"
def fmt_percent(value): return f"{fmt_number(value, 1)} %"
def fmt_length(value): return f"{fmt_number(value, 1)} m"
def fmt_kw(value): return f"{fmt_number(value, 1)} kW"
def fmt_rt(value): return f"{fmt_number(value, 1)} RT"
def fmt_cmd(value): return f"{fmt_number(value, 1)} ㎥/일"

def fmt_count(value):
    try:
        return f"{int(round(float(value))):,} 대"
    except Exception:
        return str(value)

def fmt_rack(value):
    try:
        return f"{int(round(float(value))):,} 식"
    except Exception:
        return str(value)

# =========================================================
# API 상태
# =========================================================
def get_api_status_df():
    return pd.DataFrame([
        ["LAND_REGULATION_API_KEY", "설정완료" if LAND_REGULATION_API_KEY else "미설정"],
        ["BUILDING_API_KEY", "설정완료" if BUILDING_API_KEY else "미설정"],
        ["KAKAO_REST_API_KEY", "설정완료" if KAKAO_REST_API_KEY else "미설정"],
    ], columns=["API", "상태"])

# =========================================================
# XML 유틸
# =========================================================
def parse_xml_root(xml_text: str):
    try:
        return ET.fromstring(xml_text)
    except Exception:
        return None

def find_text(root, tag_names):
    if root is None:
        return None
    for tag in tag_names:
        node = root.find(f".//{tag}")
        if node is not None and node.text:
            return node.text.strip()
    return None

# =========================================================
# 카카오 주소 검색
# =========================================================
@st.cache_data(show_spinner=False)
def kakao_search_address(query: str) -> Dict:
    if not query or not KAKAO_REST_API_KEY:
        return {}

    try:
        headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
        params = {"query": query}
        res = requests.get(KAKAO_ADDRESS_URL, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()

        docs = data.get("documents", [])
        if not docs:
            return {}

        d = docs[0]
        road = d.get("road_address") or {}
        jibun = d.get("address") or {}

        main_no = jibun.get("main_address_no", "")
        sub_no = jibun.get("sub_address_no", "")

        return {
            "input_address": query,
            "road_address": road.get("address_name", ""),
            "jibun_address": jibun.get("address_name", ""),
            "sido": jibun.get("region_1depth_name", ""),
            "sigungu": jibun.get("region_2depth_name", ""),
            "dong": jibun.get("region_3depth_name", ""),
            "bun": main_no,
            "ji": "" if sub_no in ["", "0", None] else sub_no,
            "mountain_yn": jibun.get("mountain_yn", "N"),
            "x": d.get("x"),
            "y": d.get("y"),
            "b_code": jibun.get("b_code", ""),
            "h_code": jibun.get("h_code", ""),
            "zone_no": road.get("zone_no", ""),
        }
    except Exception:
        return {}

# =========================================================
# 건축물대장정보 API
# =========================================================
@st.cache_data(show_spinner=False)
def get_building_register_info(address_info: Dict) -> Dict:
    if not BUILDING_API_KEY or not address_info:
        return {}

    endpoint_candidates = [
        f"{BUILDING_API_BASE}/getBrRecapTitleInfo",
        f"{BUILDING_API_BASE}/getBrTitleInfo",
    ]

    code_candidates = []
    b_code = address_info.get("b_code", "")
    h_code = address_info.get("h_code", "")
    if b_code and len(b_code) >= 10:
        code_candidates.append(b_code)
    if h_code and len(h_code) >= 10 and h_code != b_code:
        code_candidates.append(h_code)

    if not code_candidates:
        code_candidates.append("")

    common_params_base = {
        "serviceKey": BUILDING_API_KEY,
        "numOfRows": "10",
        "pageNo": "1",
        "_type": "xml",
        "platGbCd": "0" if address_info.get("mountain_yn") in ["N", "0", "", None] else "1",
        "bun": str(address_info.get("bun", "")).zfill(4),
        "ji": str(address_info.get("ji", "0")).zfill(4),
    }

    debug_logs = []

    for code in code_candidates:
        sigungu_cd = code[:5] if code else ""
        bjdong_cd = code[5:] if code else ""
        common_params = {
            **common_params_base,
            "sigunguCd": sigungu_cd,
            "bjdongCd": bjdong_cd,
        }

        for url in endpoint_candidates:
            try:
                r = requests.get(url, params=common_params, timeout=12)
                log_entry = {
                    "url": url,
                    "params": common_params,
                    "status_code": r.status_code,
                    "text_snippet": r.text[:800],
                }
                if r.status_code != 200:
                    log_entry["error"] = "http_status_not_200"
                    debug_logs.append(log_entry)
                    continue

                root = parse_xml_root(r.text)
                if root is None:
                    log_entry["error"] = "invalid_xml"
                    debug_logs.append(log_entry)
                    continue

                result = {
                    "대지면적(㎡)": float(find_text(root, ["platArea"])) if find_text(root, ["platArea"]) else None,
                    "건축면적(㎡)": float(find_text(root, ["archArea"])) if find_text(root, ["archArea"]) else None,
                    "연면적(㎡)": float(find_text(root, ["totArea"])) if find_text(root, ["totArea"]) else None,
                    "주용도": find_text(root, ["mainPurpsCdNm", "mainPurpsCd"]),
                    "_raw_xml": r.text,
                    "_debug": debug_logs,
                }
                return result
            except Exception as exc:
                debug_logs.append({
                    "url": url,
                    "params": common_params,
                    "error": str(exc),
                })

    return {"_error": "no_valid_response_from_building_api", "_debug": debug_logs}

# =========================================================
# 토지이용규제 API
# =========================================================
@st.cache_data(show_spinner=False)
def get_land_regulation_info(address_info: Dict) -> Dict:
    if not LAND_REGULATION_API_KEY or not address_info:
        return {}

    params_candidates = [
        {
            "serviceKey": LAND_REGULATION_API_KEY,
            "format": "xml",
            "addr": address_info.get("jibun_address", "") or address_info.get("road_address", ""),
        },
        {
            "ServiceKey": LAND_REGULATION_API_KEY,
            "format": "xml",
            "addr": address_info.get("jibun_address", "") or address_info.get("road_address", ""),
        },
    ]

    debug_logs = []

    for params in params_candidates:
        try:
            r = requests.get(LAND_REGULATION_URL, params=params, timeout=12)
            log_entry = {
                "url": LAND_REGULATION_URL,
                "params": params,
                "status_code": r.status_code,
                "text_snippet": r.text[:800],
            }
            if r.status_code != 200:
                log_entry["error"] = "http_status_not_200"
                debug_logs.append(log_entry)
                continue

            root = parse_xml_root(r.text)
            if root is None:
                log_entry["error"] = "invalid_xml"
                debug_logs.append(log_entry)
                continue

            zone = find_text(root, ["jijigu", "prposAreaDstrcNm", "landUseNm"])
            bcr = find_text(root, ["buldRt", "bcr", "maxBcr"])
            far = find_text(root, ["flrRt", "far", "maxFar"])
            height = find_text(root, ["height", "heightLimit", "heigtLmt"])

            return {
                "지역지구": zone if zone else "확인필요",
                "법정건폐율(%)": float(bcr) if bcr else 60.0,
                "법정용적률(%)": float(far) if far else 300.0,
                "높이제한": height if height else "개별 대지별 검토",
                "용도": "데이터센터",
                "_raw_xml": r.text,
                "_debug": debug_logs,
            }
        except Exception as exc:
            debug_logs.append({
                "url": LAND_REGULATION_URL,
                "params": params,
                "error": str(exc),
            })

    return {"_error": "no_valid_response_from_land_api", "_debug": debug_logs}

# =========================================================
# MEP 자동 추정 - 3 Tier
# =========================================================
def infer_mep_defaults(capacity_mw: float, dc_type: str) -> Dict:
    if dc_type == "AI":
        if capacity_mw < 10:
            return {"tier": "Tier 3", "rack_kw": 30, "pue": 1.25, "white_ratio": 0.36, "cooling": "수랭식", "operation": "자사용"}
        elif capacity_mw < 40:
            return {"tier": "Tier 3", "rack_kw": 45, "pue": 1.22, "white_ratio": 0.34, "cooling": "하이브리드", "operation": "자사용"}
        else:
            return {"tier": "Tier 3", "rack_kw": 60, "pue": 1.20, "white_ratio": 0.32, "cooling": "수랭식", "operation": "자사용"}
    else:
        if capacity_mw < 10:
            return {"tier": "Tier 3", "rack_kw": 6, "pue": 1.40, "white_ratio": 0.42, "cooling": "공랭식", "operation": "임대용"}
        elif capacity_mw < 40:
            return {"tier": "Tier 3", "rack_kw": 8, "pue": 1.35, "white_ratio": 0.40, "cooling": "하이브리드", "operation": "임대용"}
        else:
            return {"tier": "Tier 3", "rack_kw": 12, "pue": 1.30, "white_ratio": 0.38, "cooling": "수랭식", "operation": "임대용"}

def calculate_program(capacity_mw: float, dc_type: str, inferred: Dict) -> Dict:
    it_load_kw = capacity_mw * 1000.0
    rack_kw = inferred["rack_kw"]
    pue = inferred["pue"]
    white_ratio = inferred["white_ratio"]

    rack_count = max(1, math.ceil(it_load_kw / rack_kw))
    total_power_kw = it_load_kw * pue

    gross_area_per_mw = 950 if dc_type == "일반" else 1250
    gross_floor_area = capacity_mw * gross_area_per_mw

    white_space_area = gross_floor_area * white_ratio
    electrical_area = gross_floor_area * 0.20
    mechanical_area = gross_floor_area * 0.22
    support_area = gross_floor_area * 0.12
    circulation_area = gross_floor_area - (white_space_area + electrical_area + mechanical_area + support_area)

    return {
        "it_load_kw": it_load_kw,
        "rack_count": rack_count,
        "total_power_kw": total_power_kw,
        "gross_floor_area": gross_floor_area,
        "white_space_area": white_space_area,
        "electrical_area": electrical_area,
        "mechanical_area": mechanical_area,
        "support_area": support_area,
        "circulation_area": circulation_area,
        "ups_capacity_kw": it_load_kw * 1.15,
        "cooling_rt": total_power_kw / 3.517,
        "water_supply_cmd": capacity_mw * (18 if dc_type == "일반" else 28),
    }

# =========================================================
# 결과 생성
# =========================================================
def generate_architecture_summary(address: str, capacity_mw: float, dc_type: str, prog: Dict,
                                  address_info: Dict, building_info: Dict, land_info: Dict) -> Dict:
    if dc_type == "AI":
        above, below, floor_h = (5, 2, 6.5) if capacity_mw < 20 else (6, 2, 6.5)
    else:
        above, below, floor_h = (4, 1, 5.8) if capacity_mw < 20 else (5, 1, 5.8)

    gross_area = prog["gross_floor_area"]
    floor_count = above + below
    footprint = gross_area / floor_count

    legal_bcr = land_info.get("법정건폐율(%)", 60.0) if land_info else 60.0
    assumed_bcr = min(40.0, legal_bcr) / 100.0 if isinstance(legal_bcr, (int, float)) else 0.4

    site_area = building_info.get("대지면적(㎡)") or (footprint / assumed_bcr)
    bld_area = building_info.get("건축면적(㎡)") or footprint
    total_area = building_info.get("연면적(㎡)") or prog["gross_floor_area"]

    bcr = (bld_area / site_area) * 100 if site_area else 0
    far = (total_area / site_area) * 100 if site_area else 0
    height = above * floor_h
    landscape_area = site_area * 0.15 if site_area else 0
    parking_count = max(10, math.ceil(total_area / 450))

    floors = []
    for i in range(below, 0, -1):
        floors.append([f"B{i}", footprint])
    for i in range(1, above + 1):
        floors.append([f"{i}F", footprint])

    return {
        "용도": building_info.get("주용도") or land_info.get("용도") or "데이터센터",
        "주소": address_info.get("road_address") or address_info.get("jibun_address") or address,
        "층수": f"지하 {below}층 / 지상 {above}층",
        "대지면적(㎡)": site_area,
        "건축면적(㎡)": bld_area,
        "건폐율(%)": bcr,
        "연면적(㎡)": total_area,
        "용적률(%)": far,
        "높이(m)": height,
        "층고(m)": floor_h,
        "주차대수(대)": parking_count,
        "조경면적(㎡)": landscape_area,
        "층별면적": floors
    }

def generate_space_program(prog: Dict) -> pd.DataFrame:
    ws = prog["white_space_area"]
    el = prog["electrical_area"]
    me = prog["mechanical_area"]
    su = prog["support_area"]
    ci = prog["circulation_area"]

    rows = [
        ["전산시설", "전산실", fmt_area(ws * 0.68)],
        ["전산시설", "항온항습실", fmt_area(ws * 0.10)],
        ["전산시설", "전산기계실", fmt_area(ws * 0.14)],
        ["전산시설", "설비샤프트", fmt_area(ws * 0.08)],
        ["기반시설", "수변전실", fmt_area(el * 0.22)],
        ["기반시설", "발전기실", fmt_area(el * 0.22)],
        ["기반시설", "배터리실", fmt_area(el * 0.10)],
        ["기반시설", "UPS실", fmt_area(el * 0.18)],
        ["기반시설", "기계실", fmt_area(me * 0.55)],
        ["기반시설", "소화가스실", fmt_area(el * 0.05)],
        ["기반시설", "항온항습실", fmt_area(me * 0.12)],
        ["기반시설", "보조연료탱크실", fmt_area(el * 0.08)],
        ["기반시설", "화물승강기", fmt_area(ci * 0.06)],
        ["지원시설", "운영실", fmt_area(su * 0.18)],
        ["지원시설", "회의실", fmt_area(su * 0.08)],
        ["지원시설", "보안실", fmt_area(su * 0.10)],
        ["지원시설", "종합상황실", fmt_area(su * 0.14)],
        ["지원시설", "방재센터", fmt_area(su * 0.10)],
        ["지원시설", "하역장", fmt_area(su * 0.20)],
        ["지원시설", "포장해체실", fmt_area(su * 0.10)],
    ]
    return pd.DataFrame(rows, columns=["구분", "세부공간", "면적"])

def generate_law_review(address: str, arch: Dict, address_info: Dict, land_info: Dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if not address.strip():
        return pd.DataFrame(columns=["항목", "내용"]), pd.DataFrame(columns=["법규항목", "관련법규", "법정기준", "계획값", "검토결과"])

    legal_bcr = land_info.get("법정건폐율(%)", 60.0)
    legal_far = land_info.get("법정용적률(%)", 300.0)
    legal_height = land_info.get("높이제한", "개별 대지별 검토")

    site_info = pd.DataFrame([
        ["사이트 주소", arch.get("주소", address)],
        ["위치", f"{address_info.get('sido','')} {address_info.get('sigungu','')} {address_info.get('dong','')}".strip()],
        ["지역·지구", land_info.get("지역지구", "확인필요")],
        ["용도", arch.get("용도", "데이터센터")],
    ], columns=["항목", "내용"])

    legal_parking = max(1, math.ceil(arch["연면적(㎡)"] / 800))

    rows = [
        ["법정건폐율 / 계획건폐율", "건축법 및 지자체 조례", fmt_percent(legal_bcr), fmt_percent(arch["건폐율(%)"]), "적합" if arch["건폐율(%)"] <= legal_bcr else "추가 검토필요"],
        ["법정용적률 / 계획용적률", "국토계획법 및 지자체 조례", fmt_percent(legal_far), fmt_percent(arch["용적률(%)"]), "적합" if arch["용적률(%)"] <= legal_far else "추가 검토필요"],
        ["높이제한", "건축법 / 지구단위 / 경관", str(legal_height), fmt_length(arch["높이(m)"]), "추가 검토필요"],
        ["법정주차대수", "주차장법 및 조례", fmt_count(legal_parking), fmt_count(arch["주차대수(대)"]), "적합" if arch["주차대수(대)"] >= legal_parking else "추가 검토필요"],
        ["대지안의 공지", "건축법 및 건축조례", "인접대지경계선/건축선 확인", "-", "추가 검토필요"],
        ["일조사선", "정북일조/채광일조", "대상 여부 확인", "-", "해당/추가 검토필요"],
        ["지역·지구 건축행위제한", "토지이용규제 관련 법령 및 조례", "허용 여부 확인", arch.get("용도", "데이터센터"), "추가 검토필요"],
        ["법정조경면적", "지자체 조례", "대지면적 기준 산정", fmt_area(arch["조경면적(㎡)"]), "추가 검토필요"],
        ["공개공지", "관련 법령 및 조례", "해당 시 확보", "-", "해당없음"],
    ]
    return site_info, pd.DataFrame(rows, columns=["법규항목", "관련법규", "법정기준", "계획값", "검토결과"])

def generate_mep_overview(capacity_mw: float, dc_type: str, inferred: Dict, prog: Dict, arch: Dict):
    receiving_capacity = prog["total_power_kw"] * 1.20

    if inferred["cooling"] == "공랭식":
        cooling_location = "옥상 냉각설비 + 각층 기계실 + 지상 발전기 구역 연계"
    elif inferred["cooling"] == "수랭식":
        cooling_location = "옥상 냉각탑/드라이쿨러 + 지하 또는 지상 기계실 + 샤프트 수직배관"
    else:
        cooling_location = "옥상/지상 냉각설비 + 지하 또는 지상 기계실 혼합 배치"

    summary = pd.DataFrame([
        ["추정 Tier", inferred["tier"]],
        ["운영방식", inferred["operation"]],
        ["추정 랙당 전력", fmt_kw(inferred["rack_kw"])],
        ["목표 PUE", f"{float(inferred['pue']):.2f}"],
        ["전산실 비율", fmt_percent(inferred["white_ratio"] * 100)],
        ["냉각방식", inferred["cooling"]],
        ["필요 전력량", fmt_kw(prog["total_power_kw"])],
        ["확보 필요 수전용량", fmt_kw(receiving_capacity)],
        ["UPS 용량", fmt_kw(prog["ups_capacity_kw"])],
        ["랙 수량", fmt_rack(prog["rack_count"])],
        ["랙 전력밀도", f"{fmt_kw(prog['it_load_kw'] / prog['rack_count'])}/랙"],
        ["상수도 공급량", fmt_cmd(prog["water_supply_cmd"])],
        ["예상 냉각부하", fmt_rt(prog["cooling_rt"])],
        ["냉각설비/기계실 배치", cooling_location],
    ], columns=["항목", "값"])

    area_df = pd.DataFrame([
        ["전체 연면적", fmt_area(arch["연면적(㎡)"])],
        ["전산실", fmt_area(prog["white_space_area"] * 0.68)],
        ["항온항습실", fmt_area(prog["white_space_area"] * 0.10)],
        ["전산기계실", fmt_area(prog["white_space_area"] * 0.14)],
        ["기반시설", fmt_area(prog["electrical_area"] + prog["mechanical_area"])],
        ["지원시설", fmt_area(prog["support_area"])],
    ], columns=["구분", "면적"])

    floor_area_df = pd.DataFrame(
        [[floor, fmt_area(area)] for floor, area in arch["층별면적"]],
        columns=["층", "층별면적"]
    )

    ratio_total = arch["연면적(㎡)"]
    ratio_df = pd.DataFrame([
        ["전산시설", fmt_percent(prog["white_space_area"] / ratio_total * 100)],
        ["전기시설", fmt_percent(prog["electrical_area"] / ratio_total * 100)],
        ["기계시설", fmt_percent(prog["mechanical_area"] / ratio_total * 100)],
        ["지원시설", fmt_percent(prog["support_area"] / ratio_total * 100)],
        ["공용/순환", fmt_percent(prog["circulation_area"] / ratio_total * 100)],
    ], columns=["설비부문", "비율"])

    return summary, area_df, floor_area_df, ratio_df

# =========================================================
# 레이아웃
# =========================================================
left_col, right_col = st.columns([3, 7], gap="medium")

with left_col:
    st.markdown('<div class="left-panel">', unsafe_allow_html=True)

    st.markdown('<div class="logo-box">', unsafe_allow_html=True)
    st.image("haeahn_logo.png", width=170)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="app-title">HAEAHN PCM Datacenter Solution</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">조건입력</div>', unsafe_allow_html=True)
    address = st.text_input("주소 입력", placeholder="예: 서울시 강남구 삼성동 ...")
    capacity_mw = st.number_input("규모 입력 (MW)", min_value=0.0, value=20.0, step=1.0)
    dc_type = st.radio("일반 / AI 선택", ["일반 데이터센터", "AI 데이터센터"], horizontal=True)
    run = st.button("검토 실행", type="primary", use_container_width=True)

    st.markdown('<div class="section-title">API 현황</div>', unsafe_allow_html=True)
    st.dataframe(get_api_status_df(), use_container_width=True, hide_index=True)

    if run and address.strip():
        address_info = kakao_search_address(address)
        building_info = get_building_register_info(address_info)
        land_info = get_land_regulation_info(address_info)
        
        st.markdown('<div class="section-title">디버그: API 응답</div>', unsafe_allow_html=True)
        with st.expander("상세 조회 (접기 가능)", expanded=False):
            st.write("주소 검색 결과:", address_info)
            st.write("건축물대장 응답 요약:", {k:v for k,v in (building_info or {}).items() if k not in ['_raw_xml', '_debug']})
            if isinstance(building_info, dict) and building_info.get("_raw_xml"):
                st.code(building_info.get("_raw_xml")[:3000], language='xml')
            if isinstance(building_info, dict) and building_info.get("_debug"):
                st.write("건축물대장 디버그 로그:", building_info.get("_debug"))

            st.write("토지규제 응답 요약:", {k:v for k,v in (land_info or {}).items() if k not in ['_raw_xml', '_debug']})
            if isinstance(land_info, dict) and land_info.get("_raw_xml"):
                st.code(land_info.get("_raw_xml")[:3000], language='xml')
            if isinstance(land_info, dict) and land_info.get("_debug"):
                st.write("토지규제 디버그 로그:", land_info.get("_debug"))

    st.markdown('</div>', unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="right-panel">', unsafe_allow_html=True)

    if run and address.strip():
        inferred = infer_mep_defaults(capacity_mw, dc_type)
        prog = calculate_program(capacity_mw, dc_type, inferred)
        arch = generate_architecture_summary(address, capacity_mw, dc_type, prog, address_info, building_info, land_info)
        space_df = generate_space_program(prog)
        site_info_df, law_df = generate_law_review(address, arch, address_info, land_info)
        mep_summary_df, mep_area_df, mep_floor_df, mep_ratio_df = generate_mep_overview(capacity_mw, dc_type, inferred, prog, arch)
    elif run:
        inferred = infer_mep_defaults(capacity_mw, dc_type)
        prog = calculate_program(capacity_mw, dc_type, inferred)
        arch = generate_architecture_summary("", capacity_mw, dc_type, prog, {}, {}, {})
        space_df = generate_space_program(prog)
        site_info_df = pd.DataFrame()
        law_df = pd.DataFrame()
        mep_summary_df, mep_area_df, mep_floor_df, mep_ratio_df = generate_mep_overview(capacity_mw, dc_type, inferred, prog, arch)
    else:
        arch = {}
        space_df = pd.DataFrame()
        site_info_df = pd.DataFrame()
        law_df = pd.DataFrame()
        mep_summary_df = pd.DataFrame()
        mep_area_df = pd.DataFrame()
        mep_floor_df = pd.DataFrame()
        mep_ratio_df = pd.DataFrame()

    tab1, tab2, tab3, tab4 = st.tabs(["건축개요", "법규검토", "설비개요", "2D/3D"])

    with tab1:
        st.subheader("건축개요")
        if not run:
            st.info("좌측 조건을 입력 후 검토 실행을 눌러주세요.")
        else:
            arch_df = pd.DataFrame([
                ["용도", arch["용도"]],
                ["주소", arch["주소"]],
                ["층수", arch["층수"]],
                ["대지면적", fmt_area(arch["대지면적(㎡)"])],
                ["건축면적", fmt_area(arch["건축면적(㎡)"])],
                ["건폐율", fmt_percent(arch["건폐율(%)"])],
                ["연면적", fmt_area(arch["연면적(㎡)"])],
                ["용적률", fmt_percent(arch["용적률(%)"])],
                ["높이", fmt_length(arch["높이(m)"])],
                ["층고", fmt_length(arch["층고(m)"])],
                ["주차대수", fmt_count(arch["주차대수(대)"])],
                ["조경면적", fmt_area(arch["조경면적(㎡)"])],
            ], columns=["항목", "값"])
            st.dataframe(arch_df, use_container_width=True, hide_index=True)
            st.markdown("#### 층별면적")
            floor_df = pd.DataFrame([[f, fmt_area(a)] for f, a in arch["층별면적"]], columns=["층", "면적"])
            st.dataframe(floor_df, use_container_width=True, hide_index=True)
            st.markdown("#### 스페이스 프로그램")
            st.dataframe(space_df, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("법규검토")
        if not run:
            st.info("조건 입력 후 검토를 실행해주세요.")
        elif not address.strip():
            st.warning("주소가 입력되지 않아 법규검토 결과를 비워둡니다.")
        else:
            st.markdown("#### 사이트 정보")
            st.dataframe(site_info_df, use_container_width=True, hide_index=True)
            st.markdown("#### 법규 검토표")
            st.dataframe(law_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("설비개요")
        if not run:
            st.info("조건 입력 후 검토를 실행해주세요.")
        else:
            st.markdown("#### 자동 추정 설비 조건")
            st.dataframe(mep_summary_df, use_container_width=True, hide_index=True)
            st.markdown("#### 전체 면적 및 세부 면적")
            st.dataframe(mep_area_df, use_container_width=True, hide_index=True)
            st.markdown("#### 층별 면적")
            st.dataframe(mep_floor_df, use_container_width=True, hide_index=True)
            st.markdown("#### 설비부문 비율")
            st.dataframe(mep_ratio_df, use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("2D/3D")
        st.info("2단계에서 구현 예정")

    st.markdown('</div>', unsafe_allow_html=True)
