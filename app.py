import math
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(
    page_title="HAEAHN PCM Datacenter Solution",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BUILDING_API_KEY = os.getenv("BUILDING_API_KEY", "").strip()
LAND_USE_INFO_API_KEY = os.getenv("LAND_USE_INFO_API_KEY", "").strip()
LAND_LAW_API_KEY = os.getenv("LAND_LAW_API_KEY", "").strip()
LAND_REGULATION_API_KEY = os.getenv("LAND_REGULATION_API_KEY", "").strip()
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "").strip()
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()

KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
BUILDING_API_BASE = "https://apis.data.go.kr/1613000/BldRgstHubService"
LAND_REGULATION_URLS = [
    "https://apis.data.go.kr/B090026/LandUseService/getInfo",
    "http://apis.data.go.kr/B090026/LandUseService/getInfo",
]
VWORLD_DATA_URL = "https://api.vworld.kr/req/data"
VWORLD_LAND_USE_LAYERS = [
    ("LT_C_UQ111", "용도지역"),
    ("LT_C_UQ112", "용도지구"),
    ("LT_C_UQ113", "용도구역"),
    ("LT_C_UQ121", "도시계획시설"),
    ("LT_C_UQ123", "기타지역지구"),
]


st.markdown(
    """
<style>
html, body, .stApp, [data-testid="stAppViewContainer"] {
    background: #f7f8fa !important;
    margin: 0 !important;
    padding: 0 !important;
}
header, footer, #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"] {
    display: none !important;
    height: 0 !important;
}
[data-testid="stAppViewContainer"], main, section.main {
    align-items: stretch !important;
    justify-content: flex-start !important;
    padding-top: 0 !important;
    margin-top: 0 !important;
}
.block-container {
    max-width: 100% !important;
    padding: 0 1.0rem 0.75rem 1.0rem !important;
    margin-top: 0 !important;
}
[data-testid="column"] {
    height: 100vh;
    min-height: 100vh;
    overflow-y: auto;
    background: #ffffff;
    border: 1px solid #d9dde5;
    padding: 12px 14px 18px 14px;
    align-items: stretch !important;
}
[data-testid="column"] > div {
    padding-top: 0 !important;
    margin-top: 0 !important;
}
[data-testid="stVerticalBlock"] {
    gap: 0 !important;
    align-content: flex-start !important;
    justify-content: flex-start !important;
}
.app-title {
    color: #163b66;
    font-size: 1.45rem;
    line-height: 1.14;
    font-weight: 800;
    margin: 0.45rem 0 0.9rem 0;
}
.section-title {
    color: #1f2937;
    font-size: 1.02rem;
    font-weight: 750;
    margin: 1rem 0 0.35rem 0;
}
.metric-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin: 8px 0 14px 0;
}
.metric-card {
    border: 1px solid #dce1e8;
    border-radius: 6px;
    padding: 10px 12px;
    background: #fbfcfe;
}
.metric-label {
    color: #5b6472;
    font-size: 0.78rem;
    margin-bottom: 4px;
}
.metric-value {
    color: #111827;
    font-size: 1.05rem;
    font-weight: 760;
}
.placeholder-box {
    border: 1px dashed #b9c1cf;
    border-radius: 6px;
    padding: 18px;
    color: #4b5563;
    background: #fafbfc;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
}
.stTabs [data-baseweb="tab"] {
    height: 40px;
    padding-left: 14px;
    padding-right: 14px;
}
button[kind="primary"], .stButton > button {
    border-radius: 6px !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def fmt_number(value, digits=1):
    if value is None or value == "":
        return "-"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_area(value):
    return f"{fmt_number(value, 1)} ㎡"


def fmt_percent(value):
    return f"{fmt_number(value, 1)} %"


def fmt_count(value, suffix="대"):
    if value is None or value == "":
        return "-"
    try:
        return f"{int(round(float(value))):,} {suffix}"
    except (TypeError, ValueError):
        return str(value)


def to_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_xml_root(xml_text: str):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None


def normalize_tag(tag):
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.strip().lower()


def find_text(root, tag_names: List[str]):
    if root is None:
        return None
    normalized_names = {normalize_tag(name.split("/")[-1]) for name in tag_names}
    for node in root.iter():
        if normalize_tag(node.tag) in normalized_names and node.text:
            return node.text.strip()
    return None


def mask_params(params: Dict) -> Dict:
    masked = {}
    for key, value in params.items():
        if "key" in key.lower():
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def build_pnu(address_info: Dict) -> str:
    b_code = str(address_info.get("b_code", ""))
    if len(b_code) < 10:
        return ""
    mountain_code = "2" if address_info.get("mountain_yn") == "Y" else "1"
    bun = str(address_info.get("bun", "") or "0").zfill(4)
    ji = str(address_info.get("ji", "") or "0").zfill(4)
    return f"{b_code[:10]}{mountain_code}{bun}{ji}"


def land_use_limits_from_zone(zone_text: str, sido: str = ""):
    zone = str(zone_text or "")
    if not zone:
        return None, None, "용도지역 미확인"

    if "제1종전용주거" in zone:
        return 50.0, 100.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "제2종전용주거" in zone:
        return 50.0, 150.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "제1종일반주거" in zone:
        return 60.0, 200.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "제2종일반주거" in zone:
        return 60.0, 250.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "제3종일반주거" in zone:
        return 50.0, 300.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "준주거" in zone:
        return 60.0, 400.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "중심상업" in zone:
        return 90.0, 1000.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "일반상업" in zone:
        return 80.0, 800.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "근린상업" in zone:
        return 70.0, 600.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "유통상업" in zone:
        return 80.0, 600.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "전용공업" in zone:
        return 70.0, 300.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "일반공업" in zone:
        return 70.0, 350.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "준공업" in zone:
        far = 400.0 if "서울" in sido else 400.0
        return 60.0, far, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "보전녹지" in zone or "생산녹지" in zone:
        return 20.0, 80.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "자연녹지" in zone:
        return 20.0, 100.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "관리지역" in zone:
        return 40.0, 100.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    if "농림지역" in zone or "자연환경보전" in zone:
        return 20.0, 80.0, "국토계획법 시행령 및 지자체 도시계획조례 기준"
    return None, None, "용도지역별 조례 기준 추가 확인필요"


def collect_vworld_zone_names(features):
    names = []
    for feature in features:
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        for key in ("uname", "jigu_name", "dstrc_nm", "name", "mnum"):
            value = properties.get(key)
            if value and str(value) not in names:
                names.append(str(value))
    return names


@st.cache_data(show_spinner=False)
def get_vworld_land_use_info(address_info: Dict) -> Dict:
    if not VWORLD_API_KEY or not address_info.get("x") or not address_info.get("y"):
        return {}

    point = f"POINT({address_info.get('x')} {address_info.get('y')})"
    debug = []
    zone_groups = []
    primary_zone = ""

    for layer, label in VWORLD_LAND_USE_LAYERS:
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": layer,
            "key": VWORLD_API_KEY,
            "domain": "localhost",
            "geomFilter": point,
            "geometry": "false",
            "format": "json",
            "size": "10",
            "crs": "EPSG:4326",
        }
        try:
            response = requests.get(VWORLD_DATA_URL, params=params, timeout=10)
            response.encoding = "utf-8"
            data = response.json()
            record = data.get("response", {}).get("record", {})
            features = (
                data.get("response", {})
                .get("result", {})
                .get("featureCollection", {})
                .get("features", [])
            )
            names = collect_vworld_zone_names(features)
            debug.append(
                {
                    "url": VWORLD_DATA_URL,
                    "layer": layer,
                    "label": label,
                    "params": mask_params(params),
                    "status_code": response.status_code,
                    "record_total": record.get("total"),
                    "names": names,
                }
            )
            if names:
                zone_groups.append(f"{label}: {', '.join(names)}")
                if label == "용도지역" and not primary_zone:
                    primary_zone = names[0]
        except Exception as exc:
            debug.append(
                {
                    "url": VWORLD_DATA_URL,
                    "layer": layer,
                    "label": label,
                    "params": mask_params(params),
                    "error": str(exc),
                }
            )

    if not zone_groups:
        return {"_error": "V-World 용도지역 조회 결과 없음", "_debug": debug}

    bcr, far, source_note = land_use_limits_from_zone(primary_zone, address_info.get("sido", ""))
    return {
        "지역지구": " / ".join(zone_groups),
        "주용도지역": primary_zone or "확인필요",
        "법정건폐율": bcr,
        "법정용적률": far,
        "높이제한": "개별 대지 및 지자체 조례 확인필요",
        "용도": "데이터센터 가능 여부는 건축법 시행령 별표1 및 지자체 조례 추가 확인",
        "정보출처": "V-World 용도지역 공간검색",
        "법정값출처": source_note,
        "_debug": debug,
    }


def api_status_df():
    rows = [
        ("건축물대장정보", BUILDING_API_KEY),
        ("토지이용정보", LAND_USE_INFO_API_KEY),
        ("토지이용규제 법령", LAND_LAW_API_KEY),
        ("토지이용규제", LAND_REGULATION_API_KEY),
        ("V-World", VWORLD_API_KEY),
        ("카카오 주소", KAKAO_REST_API_KEY),
    ]
    return pd.DataFrame(
        [{"API": name, "상태": "설정완료" if key else "미설정"} for name, key in rows]
    )


@st.cache_data(show_spinner=False)
def load_case_rows():
    for encoding in ("cp949", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv("데이터센터 사례.csv", encoding=encoding)
            label_col = "항 목" if "항 목" in df.columns else df.columns[1]
            df = df.rename(columns={label_col: "항목"})
            df["항목"] = df["항목"].fillna("").astype(str).str.strip()
            return df[df["항목"] != ""]
        except Exception:
            continue
    return pd.DataFrame()


def case_numbers(df: pd.DataFrame, keywords: List[str]) -> List[float]:
    if df.empty:
        return []
    label = df["항목"].astype(str)
    mask = pd.Series(True, index=df.index)
    for keyword in keywords:
        mask &= label.str.contains(keyword, regex=False)
    values = []
    for _, row in df[mask].iterrows():
        for column, cell in row.items():
            if column == "항목":
                continue
            number = to_float(cell)
            if number is not None and 0 < number < 1_000_000:
                values.append(number)
    return values


def benchmark_summary():
    df = load_case_rows()
    summary = {}
    candidates = {
        "건폐율": ["건", "폐", "율"],
        "용적률": ["용", "적", "률"],
        "대지면적": ["대지", "면적"],
        "연면적": ["연면적"],
        "목표 PUE": ["PUE"],
    }
    for name, keywords in candidates.items():
        values = case_numbers(df, keywords)
        if values:
            series = pd.Series(values)
            summary[name] = {
                "median": float(series.median()),
                "p25": float(series.quantile(0.25)),
                "p75": float(series.quantile(0.75)),
                "count": int(series.count()),
            }
    return summary


@st.cache_data(show_spinner=False)
def kakao_search_address(query: str) -> Dict:
    if not query or not KAKAO_REST_API_KEY:
        return {}
    try:
        response = requests.get(
            KAKAO_ADDRESS_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"},
            params={"query": query},
            timeout=10,
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
        if not documents:
            return {}
        item = documents[0]
        road = item.get("road_address") or {}
        jibun = item.get("address") or {}
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
            "ji": "" if sub_no in ("", "0", None) else sub_no,
            "mountain_yn": jibun.get("mountain_yn", "N"),
            "b_code": jibun.get("b_code", ""),
            "h_code": jibun.get("h_code", ""),
            "x": item.get("x"),
            "y": item.get("y"),
        }
    except Exception as exc:
        return {"_error": str(exc)}


@st.cache_data(show_spinner=False)
def get_building_register_info(address_info: Dict) -> Dict:
    if not BUILDING_API_KEY or not address_info:
        return {}

    code_candidates = []
    for code_key in ("b_code", "h_code"):
        code = str(address_info.get(code_key, ""))
        if len(code) >= 10 and code not in code_candidates:
            code_candidates.append(code)
    if not code_candidates:
        code_candidates.append("")

    endpoints = [
        f"{BUILDING_API_BASE}/getBrRecapTitleInfo",
        f"{BUILDING_API_BASE}/getBrTitleInfo",
    ]
    debug = []
    for code in code_candidates:
        base_params = {
            "serviceKey": BUILDING_API_KEY,
            "numOfRows": "10",
            "pageNo": "1",
            "_type": "xml",
            "sigunguCd": code[:5],
            "bjdongCd": code[5:10],
            "platGbCd": "0" if address_info.get("mountain_yn") in ("N", "0", "", None) else "1",
            "bun": str(address_info.get("bun", "")).zfill(4),
            "ji": str(address_info.get("ji", "0")).zfill(4),
        }
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, params=base_params, timeout=12)
                debug.append(
                    {
                        "url": endpoint,
                        "params": mask_params(base_params),
                        "status_code": response.status_code,
                        "snippet": response.text[:300],
                    }
                )
                if response.status_code != 200:
                    continue
                root = parse_xml_root(response.text)
                result_code = find_text(root, ["resultCode", "header/resultCode"])
                if result_code and not result_code.startswith("00"):
                    continue
                result = {
                    "대지면적": to_float(find_text(root, ["platArea"])),
                    "건축면적": to_float(find_text(root, ["archArea"])),
                    "연면적": to_float(find_text(root, ["totArea"])),
                    "주용도": find_text(root, ["mainPurpsCdNm", "mainPurpsCd"]),
                    "건물명": find_text(root, ["bldNm"]),
                    "_debug": debug,
                }
                if any(result.get(key) for key in ("대지면적", "건축면적", "연면적")):
                    return result
            except Exception as exc:
                debug.append({"url": endpoint, "params": mask_params(base_params), "error": str(exc)})
    return {"_error": "건축물대장 조회 결과 없음", "_debug": debug}


@st.cache_data(show_spinner=False)
def get_land_regulation_info(address_info: Dict) -> Dict:
    if not address_info:
        return {}
    key_candidates = []
    for name, key in (
        ("LAND_USE_INFO_API_KEY", LAND_USE_INFO_API_KEY),
        ("LAND_LAW_API_KEY", LAND_LAW_API_KEY),
        ("LAND_REGULATION_API_KEY", LAND_REGULATION_API_KEY),
    ):
        if key and key not in [item["key"] for item in key_candidates]:
            key_candidates.append({"name": name, "key": key})
    if not key_candidates:
        return {}

    address = address_info.get("jibun_address") or address_info.get("road_address")
    if not address:
        return {"_error": "주소 없음", "_debug": []}

    debug = []
    pnu = build_pnu(address_info)
    for url in LAND_REGULATION_URLS:
        for key_item in key_candidates:
            for key_name in ("serviceKey", "ServiceKey"):
                for type_name in ("format", "_type"):
                    params_candidates = [
                        {key_name: key_item["key"], type_name: "xml", "addr": address},
                    ]
                    if pnu:
                        params_candidates.append({key_name: key_item["key"], type_name: "xml", "pnu": pnu})

                    for params in params_candidates:
                        try:
                            response = requests.get(
                                url,
                                params=params,
                                headers={"Accept": "application/xml"},
                                timeout=12,
                            )
                            debug.append(
                                {
                                    "url": url,
                                    "key_source": key_item["name"],
                                    "params": mask_params(params),
                                    "status_code": response.status_code,
                                    "snippet": response.text[:300],
                                }
                            )
                            if response.status_code != 200:
                                continue
                            root = parse_xml_root(response.text)
                            if root is None:
                                continue
                            result_code = find_text(root, ["resultCode", "header/resultCode"])
                            if result_code and not result_code.startswith("00"):
                                continue
                            zone = find_text(root, ["jijigu", "prposAreaDstrcNm", "landUseNm", "useDistrict"])
                            bcr = to_float(find_text(root, ["buldRt", "bcr", "maxBcr"]))
                            far = to_float(find_text(root, ["flrRt", "far", "maxFar"]))
                            height = find_text(root, ["height", "heightLimit", "heightLmt", "heigtLmt"])
                            if not any([zone, bcr, far, height]):
                                continue
                            if zone and (bcr is None or far is None):
                                mapped_bcr, mapped_far, source_note = land_use_limits_from_zone(
                                    zone,
                                    address_info.get("sido", ""),
                                )
                                bcr = bcr or mapped_bcr
                                far = far or mapped_far
                            else:
                                source_note = "토지이용규제 API 응답값"
                            return {
                                "지역지구": zone or "확인필요",
                                "주용도지역": zone or "확인필요",
                                "법정건폐율": bcr,
                                "법정용적률": far,
                                "높이제한": height or "개별 대지 및 지자체 조례 확인필요",
                                "용도": "데이터센터 가능 여부는 건축법 시행령 별표1 및 지자체 조례 추가 확인",
                                "정보출처": "토지이용규제 API",
                                "법정값출처": source_note,
                                "_debug": debug,
                            }
                        except Exception as exc:
                            debug.append(
                                {
                                    "url": url,
                                    "key_source": key_item["name"],
                                    "params": mask_params(params),
                                    "error": str(exc),
                                }
                            )

    vworld_info = get_vworld_land_use_info(address_info)
    if vworld_info and not vworld_info.get("_error"):
        vworld_info["_debug"] = debug + vworld_info.get("_debug", [])
        vworld_info["_fallback_reason"] = "토지이용규제 API가 유효한 법정 건폐율/용적률 정보를 반환하지 않음"
        return vworld_info

    return {
        "_error": "토지이용규제 조회 실패",
        "_message": "토지이용규제 API와 V-World 보조 조회가 모두 실패했습니다.",
        "_debug": debug + (vworld_info.get("_debug", []) if isinstance(vworld_info, dict) else []),
    }


def infer_mep_defaults(dc_type: str):
    if dc_type == "AI":
        return {
            "rack_kw": 45,
            "pue": 1.24,
            "white_ratio": 0.32,
            "cooling": "Direct-to-Chip 수랭 + 보조 공랭 하이브리드",
            "ups_minutes": 10,
            "generator_hours": 48,
            "chilled_water_dt": 6.0,
            "chilled_water_supply_c": 18.0,
            "chilled_water_return_c": 24.0,
            "condenser_water_supply_c": 32.0,
            "condenser_water_return_c": 37.0,
            "water_cmd_per_mw": 28.0,
            "electrical_redundancy": "2N 또는 Distributed Redundant",
            "mechanical_redundancy": "N+1",
            "room_supply_temp_c": 24.0,
            "room_return_temp_c": 36.0,
        }
    return {
        "rack_kw": 10,
        "pue": 1.40,
        "white_ratio": 0.38,
        "cooling": "공랭식 CRAH + 냉동기/냉각탑",
        "ups_minutes": 15,
        "generator_hours": 24,
        "chilled_water_dt": 5.0,
        "chilled_water_supply_c": 7.0,
        "chilled_water_return_c": 12.0,
        "condenser_water_supply_c": 30.0,
        "condenser_water_return_c": 35.0,
        "water_cmd_per_mw": 18.0,
        "electrical_redundancy": "N+1",
        "mechanical_redundancy": "N+1",
        "room_supply_temp_c": 24.0,
        "room_return_temp_c": 32.0,
    }


def estimate_program(capacity_mw: float, dc_type: str):
    defaults = infer_mep_defaults(dc_type)
    gross_area_per_mw = 3200 if dc_type == "AI" else 4300
    gross_area = max(capacity_mw * gross_area_per_mw, 1200)
    floor_count = max(3, min(12, math.ceil(gross_area / 5500)))
    floor_area = gross_area / floor_count

    ratio = {
        "전산실": 0.30 if dc_type == "AI" else 0.28,
        "전산기계실": 0.08,
        "항온항습실": 0.08 if dc_type == "AI" else 0.07,
        "설비샤프트": 0.04,
        "수변전실/전기실": 0.10,
        "발전기실": 0.07,
        "배터리실/UPS실": 0.09 if dc_type == "AI" else 0.08,
        "기계실": 0.12 if dc_type == "AI" else 0.10,
        "소화가스실/연료탱크": 0.04,
        "지원시설": 0.08 if dc_type == "AI" else 0.10,
        "공용/코어": 0.00 if dc_type == "AI" else 0.04,
    }
    ratio_total = sum(ratio.values())
    spaces = []
    for name, share in ratio.items():
        normalized_share = share / ratio_total
        spaces.append(
            {
                "구분": name,
                "면적(㎡)": round(gross_area * normalized_share, 1),
                "비율(%)": round(normalized_share * 100, 1),
            }
        )

    rack_count = capacity_mw * 1000 / defaults["rack_kw"]
    power_kw = capacity_mw * 1000 * defaults["pue"]
    cooling_rt = power_kw * 0.284
    return {
        "gross_area": gross_area,
        "floor_count": floor_count,
        "floor_area": floor_area,
        "spaces": spaces,
        "rack_count": rack_count,
        "rack_kw": defaults["rack_kw"],
        "pue": defaults["pue"],
        "power_kw": power_kw,
        "cooling_rt": cooling_rt,
        "cooling": defaults["cooling"],
    }


def make_floor_height_plan(floor_count: int, building_area: float, far_area: float) -> List[Dict]:
    above_floor_area = far_area / floor_count if floor_count else 0
    return [
        {
            "floor": "B2",
            "program": "발전기실",
            "area": building_area,
            "height": 9.0,
        },
        {
            "floor": "B1",
            "program": "수변전실/전기실",
            "area": building_area,
            "height": 7.5,
        },
        {
            "floor": "1F",
            "program": "입구, 로비, 사무실, 보안실, 하역장",
            "area": above_floor_area,
            "height": 4.5,
        },
        *[
            {
                "floor": f"{floor}F",
                "program": "전산실, 항온항습실, 전산기계실, UPS/배터리실"
                if floor < floor_count
                else "전산실, 기계실, 냉각설비, 옥상 장비 연계",
                "area": above_floor_area,
                "height": 6.0,
            }
            for floor in range(2, floor_count + 1)
        ],
    ]


def floor_meta_map(floor_plan: List[Dict]) -> Dict[str, Dict]:
    return {item["floor"]: item for item in floor_plan}


def estimate_architecture(capacity_mw: float, dc_type: str, building_info: Dict, land_info: Dict):
    program = estimate_program(capacity_mw, dc_type)
    legal_bcr = land_info.get("법정건폐율") or 60.0
    legal_far = land_info.get("법정용적률") or 300.0
    site_area = building_info.get("대지면적") or max(program["gross_area"] / (legal_far / 100) * 1.12, 1800)
    planned_far_area = min(program["gross_area"], site_area * legal_far / 100 * 0.92)
    planned_building_area = min(program["floor_area"], site_area * legal_bcr / 100 * 0.88)
    planned_bcr = planned_building_area / site_area * 100
    planned_far = planned_far_area / site_area * 100
    parking_count = max(1, math.ceil(planned_far_area / 200))
    landscape_area = site_area * 0.15 if site_area >= 200 else 0
    floor_plan = make_floor_height_plan(program["floor_count"], planned_building_area, planned_far_area)
    above_ground_height = sum(item["height"] for item in floor_plan if not item["floor"].startswith("B"))
    return {
        **program,
        "site_area": site_area,
        "building_area": planned_building_area,
        "far_area": planned_far_area,
        "bcr": planned_bcr,
        "far": planned_far,
        "parking_count": parking_count,
        "landscape_area": landscape_area,
        "basement_count": 2,
        "height": above_ground_height,
        "floor_height": 6.0,
        "floor_height_note": "B2 9.0m / B1 7.5m / 1F 4.5m / 2F 이상 6.0m",
        "floor_plan": floor_plan,
    }


def area_from_spaces(spaces: List[Dict], names: List[str]) -> float:
    return sum(
        float(item.get("면적(㎡)", 0) or 0)
        for item in spaces
        if item.get("구분") in names
    )


def make_overseas_case_rows(dc_type: str) -> List[Dict]:
    rows = [
        {
            "사례": "Google 글로벌 데이터센터 플릿",
            "기준일": "2024 / 2025-2026 공개",
            "핵심지표": "TTM PUE 1.09, 업계 평균 1.56 대비 저오버헤드",
            "설계반영": "일반형은 1.40, AI형은 1.24 목표로 보수 적용",
        },
        {
            "사례": "Google 물 관리 전략",
            "기준일": "2025 공개",
            "핵심지표": "고수위험 지역은 공랭 또는 재생수 우선 검토",
            "설계반영": "AI형은 폐회로 수랭, 일반형은 지역 조건별 공랭/냉수식 병행",
        },
        {
            "사례": "Frontier 액체냉각 최적화 연구",
            "기준일": "2026-03",
            "핵심지표": "유량+공급수온 최적화 시 총 에너지 27.8% 절감",
            "설계반영": "AI형에 CDU 수온/유량 제어형 수랭 기본값 반영",
        },
    ]
    if dc_type == "AI":
        rows.append(
            {
                "사례": "H100 액체냉각 벤치마크",
                "기준일": "2025-07",
                "핵심지표": "액체냉각 GPU 41~50°C, 공랭 54~72°C, 성능 17% 향상",
                "설계반영": "AI 랙 전력밀도 45 kW/rack, D2C 수랭 전제",
            }
        )
    return rows


def estimate_mep(capacity_mw: float, dc_type: str, operation_type: str, arch: Dict) -> Dict:
    defaults = infer_mep_defaults(dc_type)
    it_load_kw = capacity_mw * 1000
    total_power_kw = arch["power_kw"]
    non_it_kw = max(total_power_kw - it_load_kw, 0)
    white_space_area = area_from_spaces(arch["spaces"], ["전산실"])
    electrical_area = area_from_spaces(arch["spaces"], ["수변전실/전기실", "발전기실", "배터리실/UPS실"])
    mechanical_area = area_from_spaces(arch["spaces"], ["전산기계실", "항온항습실", "기계실", "설비샤프트"])
    support_area = area_from_spaces(arch["spaces"], ["지원시설", "공용/코어", "소화가스실/연료탱크"])
    rack_count = max(arch["rack_count"], 1)
    rack_kw = arch["rack_kw"]
    power_density_w_m2 = (it_load_kw * 1000 / white_space_area) if white_space_area else None
    critical_load_kw = it_load_kw * (1.10 if dc_type == "AI" else 1.08)
    ups_output_kw = critical_load_kw * (1.20 if dc_type == "AI" else 1.15)
    ups_output_kva = ups_output_kw / 0.9
    generator_kw = total_power_kw * (1.25 if dc_type == "AI" else 1.20)
    transformer_kva = total_power_kw / 0.92 * 1.15
    receiving_capacity_kva = transformer_kva * 1.10
    cooling_load_kw = total_power_kw
    cooling_rt = cooling_load_kw / 3.517
    chilled_water_flow_ls = cooling_load_kw / (4.186 * defaults["chilled_water_dt"])
    condenser_water_flow_ls = cooling_load_kw / (4.186 * 5.0)
    makeup_water_cmd = capacity_mw * defaults["water_cmd_per_mw"]
    cdu_share = 0.70 if dc_type == "AI" else 0.0
    air_share = 1.0 - cdu_share
    floor_meta = floor_meta_map(arch["floor_plan"])
    b2_area = floor_meta.get("B2", {}).get("area", arch["building_area"])
    b1_area = floor_meta.get("B1", {}).get("area", arch["building_area"])
    top_floor = f"{arch['floor_count']}F"
    top_floor_area = floor_meta.get(top_floor, {}).get("area", arch["far_area"] / arch["floor_count"])
    office_hvac = "전용 AHU + FCU" if operation_type == "자사용" else "전용 AHU + VAV"
    load_bank_kw = generator_kw * 0.25
    fuel_tank_l = generator_kw * defaults["generator_hours"] * 0.24
    chiller_plant_rt = cooling_rt * (1.15 if dc_type == "AI" else 1.10)
    datahall_cooling_rt = cooling_rt * (0.70 if dc_type == "AI" else 0.62)
    ut_cooling_rt = cooling_rt - datahall_cooling_rt
    buffer_tank_m3 = max(capacity_mw * (2.5 if dc_type == "AI" else 1.8), 10)
    humidifier_kg_h = white_space_area * (0.18 if dc_type == "AI" else 0.12)
    dehumidifier_l_h = white_space_area * (0.15 if dc_type == "AI" else 0.10)

    electrical_rows = [
        {"항목": "IT 부하", "계획값": f"{fmt_number(it_load_kw, 1)} kW", "산정기준": "입력 IT 용량"},
        {"항목": "총 시설부하", "계획값": f"{fmt_number(total_power_kw, 1)} kW", "산정기준": f"IT 부하 × PUE {fmt_number(arch['pue'], 2)}"},
        {"항목": "비IT 부하", "계획값": f"{fmt_number(non_it_kw, 1)} kW", "산정기준": "총 시설부하 - IT 부하"},
        {"항목": "수전용량", "계획값": f"{fmt_number(transformer_kva, 1)} kVA", "산정기준": "변압기 합계용량"},
        {"항목": "확보가능 수전용량", "계획값": f"{fmt_number(receiving_capacity_kva, 1)} kVA", "산정기준": "수전 요구용량 기준"},
        {"항목": "예상 랙 수량", "계획값": f"{fmt_number(rack_count, 0)} rack", "산정기준": f"IT 부하 ÷ {fmt_number(rack_kw, 1)} kW/rack"},
        {"항목": "데이터홀 랙당 전력", "계획값": f"{fmt_number(rack_kw, 1)} kW/rack", "산정기준": "실별 기본 기준값"},
        {"항목": "랙 전력 밀도", "계획값": f"{fmt_number(power_density_w_m2, 0)} W/㎡" if power_density_w_m2 else "-", "산정기준": "IT 부하 ÷ 데이터홀 면적"},
        {"항목": "UPS 정격용량", "계획값": f"{fmt_number(ups_output_kva, 1)} kVA", "산정기준": f"Critical Load × 여유율, {defaults['ups_minutes']}분 자율운전"},
        {"항목": "변압기 합계용량", "계획값": f"{fmt_number(transformer_kva, 1)} kVA", "산정기준": "총 시설부하 / PF 0.92 × 1.15"},
        {"항목": "수전 요구용량", "계획값": f"{fmt_number(receiving_capacity_kva, 1)} kVA", "산정기준": "변압기 합계 × 1.10"},
        {"항목": "비상발전기 용량", "계획값": f"{fmt_number(generator_kw / 1000, 2)} MW", "산정기준": f"총 시설부하 × {'1.25' if dc_type == 'AI' else '1.20'}"},
        {"항목": "Load Bank", "계획값": f"{fmt_number(load_bank_kw, 1)} kW", "산정기준": "발전기 시험부하 25% 가정"},
        {"항목": "전기 이중화", "계획값": defaults["electrical_redundancy"], "산정기준": "MEP 계획 기준"},
    ]

    mechanical_rows = [
        {"항목": "데이터홀 면적", "계획값": fmt_area(white_space_area), "산정기준": "전산실 합계"},
        {"항목": "총 냉각부하", "계획값": f"{fmt_number(cooling_load_kw, 1)} kW", "산정기준": "총 시설부하 전량 열부하 가정"},
        {"항목": "총 냉각용량", "계획값": f"{fmt_number(cooling_rt, 1)} RT", "산정기준": "냉각부하 ÷ 3.517"},
        {"항목": "예상냉각부하 RT", "계획값": f"{fmt_number(cooling_rt, 1)} RT", "산정기준": "운영 표기 항목"},
        {"항목": "Chiller Plant", "계획값": f"{fmt_number(chiller_plant_rt, 1)} RT", "산정기준": "총 냉각용량 × 여유율"},
        {"항목": "데이터홀 Cooling", "계획값": f"{fmt_number(datahall_cooling_rt, 1)} RT", "산정기준": "데이터홀 부하 분담"},
        {"항목": "UT Cooling", "계획값": f"{fmt_number(ut_cooling_rt, 1)} RT", "산정기준": "지원/공조/UT 부하 분담"},
        {"항목": "냉각 방식", "계획값": defaults["cooling"], "산정기준": "유형별 기본값"},
        {"항목": "전산실 공급/환기온도", "계획값": f"{fmt_number(defaults['room_supply_temp_c'], 1)} / {fmt_number(defaults['room_return_temp_c'], 1)} °C", "산정기준": "설계 목표값"},
        {"항목": "냉수 공급/환수온도", "계획값": f"{fmt_number(defaults['chilled_water_supply_c'], 1)} / {fmt_number(defaults['chilled_water_return_c'], 1)} °C", "산정기준": f"ΔT {fmt_number(defaults['chilled_water_dt'], 1)} °C"},
        {"항목": "냉수 순환유량", "계획값": f"{fmt_number(chilled_water_flow_ls, 1)} L/s", "산정기준": "Q = m·Cp·ΔT"},
        {"항목": "열원측 순환유량", "계획값": f"{fmt_number(condenser_water_flow_ls, 1)} L/s", "산정기준": "열원측 ΔT 5°C 가정"},
        {"항목": "보충수 계획량", "계획값": f"{fmt_number(makeup_water_cmd, 1)} ㎥/day", "산정기준": f"{fmt_number(defaults['water_cmd_per_mw'], 1)} ㎥/day·MW"},
        {"항목": "상수도 공급량", "계획값": f"{fmt_number(makeup_water_cmd, 1)} ㎥/day", "산정기준": "보충수 계획량과 동일"},
        {"항목": "사무실 공조방식", "계획값": office_hvac, "산정기준": f"{operation_type} 운영 기준"},
        {"항목": "Dehumidifier", "계획값": f"{fmt_number(dehumidifier_l_h, 1)} L/h", "산정기준": "전산실 면적 연동"},
        {"항목": "Humidifier", "계획값": f"{fmt_number(humidifier_kg_h, 1)} kg/h", "산정기준": "전산실 면적 연동"},
        {"항목": "Buffer Tank", "계획값": f"{fmt_number(buffer_tank_m3, 1)} ㎥", "산정기준": "유형별 축열·완충 기준"},
        {"항목": "기계 이중화", "계획값": defaults["mechanical_redundancy"], "산정기준": "MEP 계획 기준"},
        {"항목": "냉각 분담", "계획값": f"수랭 {fmt_percent(cdu_share * 100) if dc_type == 'AI' else '0.0 %'} / 공랭 {fmt_percent(air_share * 100)}", "산정기준": "AI는 D2C+보조공랭, 일반은 공랭 중심"},
    ]

    space_rows = [
        {"구역": "전산실", "면적": fmt_area(white_space_area), "비고": f"전력밀도 {fmt_number(power_density_w_m2, 0)} W/㎡" if power_density_w_m2 else "-"},
        {"구역": "전기계통", "면적": fmt_area(electrical_area), "비고": "수전, UPS, 배터리, 발전기"},
        {"구역": "기계계통", "면적": fmt_area(mechanical_area), "비고": "항온항습, 기계실, 샤프트, CDU"},
        {"구역": "지원/공용", "면적": fmt_area(support_area), "비고": "운영지원, 방재, 공용코어"},
    ]

    placement_rows = [
        {"분야": "전기", "권장 배치": "B1 수변전실 / UPS·배터리실, B2 발전기실", "설계 포인트": "수전-UPS-전산실 수직 샤프트 최단화, 연료/배기 동선 분리"},
        {"분야": "기계", "권장 배치": "최상층 기계실·CDU, 옥상 열원설비, B2 소방·저수조", "설계 포인트": "냉각탑·드라이쿨러 옥상 배치, 대형장비 반입동선 확보"},
        {"분야": "전산", "권장 배치": "2F 이상 데이터홀 집중", "설계 포인트": "AI형은 수랭 매니폴드 존 분리, 일반형은 CRAH 균등배치"},
    ]

    equipment_rows = [
        {"설비": "변전실", "권장 위치": "B1", "권장 면적": fmt_area(electrical_area * 0.30), "층고": f"{fmt_number(floor_meta.get('B1', {}).get('height', 7.5), 1)} m"},
        {"설비": "발전기", "권장 위치": "B2", "권장 면적": fmt_area(electrical_area * 0.35), "층고": f"{fmt_number(floor_meta.get('B2', {}).get('height', 9.0), 1)} m"},
        {"설비": "연료탱크", "권장 위치": "B2 또는 외부 연료저장구역", "권장 면적": fmt_area(electrical_area * 0.10), "층고": f"{fmt_number(floor_meta.get('B2', {}).get('height', 9.0), 1)} m"},
        {"설비": "Load Bank", "권장 위치": "옥상 또는 외부 서비스야드", "권장 면적": fmt_area(top_floor_area * 0.08), "층고": f"{fmt_number(floor_meta.get(top_floor, {}).get('height', 6.0), 1)} m"},
        {"설비": "Chiller Plant", "권장 위치": "옥상/최상층", "권장 면적": fmt_area(mechanical_area * 0.32), "층고": f"{fmt_number(floor_meta.get(top_floor, {}).get('height', 6.0), 1)} m"},
        {"설비": "데이터홀 Cooling", "권장 위치": "2F 이상 데이터홀 인접 전산기계실", "권장 면적": fmt_area(mechanical_area * 0.24), "층고": "6.0 m"},
        {"설비": "UT Cooling", "권장 위치": "최상층 기계실 및 공용부 인접", "권장 면적": fmt_area(mechanical_area * 0.16), "층고": f"{fmt_number(floor_meta.get(top_floor, {}).get('height', 6.0), 1)} m"},
        {"설비": "사무실 공조", "권장 위치": "1F 및 사무지원층", "권장 면적": fmt_area(support_area * 0.12), "층고": f"{fmt_number(floor_meta.get('1F', {}).get('height', 4.5), 1)} m"},
        {"설비": "Dehumidifier", "권장 위치": "데이터홀 또는 전산기계실", "권장 면적": fmt_area(mechanical_area * 0.04), "층고": "6.0 m"},
        {"설비": "Humidifier", "권장 위치": "데이터홀 또는 전산기계실", "권장 면적": fmt_area(mechanical_area * 0.04), "층고": "6.0 m"},
        {"설비": "Buffer Tank", "권장 위치": "B1 기계실 또는 최상층 기계실", "권장 면적": fmt_area(b1_area * 0.06), "층고": f"{fmt_number(floor_meta.get('B1', {}).get('height', 7.5), 1)} m"},
    ]

    return {
        "electrical_rows": electrical_rows,
        "mechanical_rows": mechanical_rows,
        "space_rows": space_rows,
        "placement_rows": placement_rows,
        "equipment_rows": equipment_rows,
        "benchmark_rows": make_overseas_case_rows(dc_type),
    }


def status_by_limit(planned, legal):
    if planned is None or legal is None:
        return "추가 검토필요"
    return "적합" if planned <= legal else "추가 검토필요"


def make_law_review(address_info: Dict, land_info: Dict, arch: Dict):
    if not address_info:
        return pd.DataFrame()
    legal_bcr = land_info.get("법정건폐율")
    legal_far = land_info.get("법정용적률")
    legal_source = land_info.get("법정값출처", "토지이용규제 API 또는 V-World 기준")
    rows = [
        {
            "법규항목": "법정건폐율 / 계획건폐율",
            "근거": f"건축법 제55조, 국토의 계획 및 이용에 관한 법률 제77조, 지자체 도시계획조례 ({legal_source})",
            "법규기준": fmt_percent(legal_bcr) if legal_bcr else "확인필요",
            "계획값": fmt_percent(arch["bcr"]),
            "검토결과": status_by_limit(arch["bcr"], legal_bcr),
        },
        {
            "법규항목": "법정용적률 / 계획용적률",
            "근거": f"건축법 제56조, 국토의 계획 및 이용에 관한 법률 제78조, 지자체 도시계획조례 ({legal_source})",
            "법규기준": fmt_percent(legal_far) if legal_far else "확인필요",
            "계획값": fmt_percent(arch["far"]),
            "검토결과": status_by_limit(arch["far"], legal_far),
        },
        {
            "법규항목": "법정주차대수",
            "근거": "주차장법 제19조, 주차장법 시행령 및 해당 지자체 주차장 설치 조례",
            "법규기준": "용도분류 확정 후 조례 기준 적용",
            "계획값": fmt_count(arch["parking_count"]),
            "검토결과": "추가 검토필요",
        },
        {
            "법규항목": "대지안의 공지",
            "근거": "건축법 제58조, 건축법 시행령 제80조의2, 지자체 건축조례",
            "법규기준": "건축선 및 인접대지경계선 이격거리 적용",
            "계획값": "대형차량 동선 및 장비 반입구 분리 필요",
            "검토결과": "추가 검토필요",
        },
        {
            "법규항목": "일조사선",
            "근거": "건축법 제61조, 건축법 시행령 제86조",
            "법규기준": "전용/일반주거지역 등 해당 시 정북일조 및 채광방향 검토",
            "계획값": land_info.get("지역지구", "확인필요"),
            "검토결과": "해당없음" if "공업" in str(land_info.get("지역지구", "")) else "추가 검토필요",
        },
        {
            "법규항목": "지역·지구 용도별 건축행위 제한",
            "근거": "국토의 계획 및 이용에 관한 법률 제76조, 건축법 시행령 별표1, 지자체 도시계획조례",
            "법규기준": "데이터센터 용도 가능 여부 확인",
            "계획값": land_info.get("용도", "데이터센터"),
            "검토결과": "추가 검토필요",
        },
        {
            "법규항목": "법정조경면적",
            "근거": "건축법 제42조, 건축법 시행령 제27조, 지자체 건축조례",
            "법규기준": "대지면적 200㎡ 이상 건축물 조경 설치",
            "계획값": fmt_area(arch["landscape_area"]),
            "검토결과": "적합" if arch["landscape_area"] > 0 else "해당없음",
        },
        {
            "법규항목": "공개공지",
            "근거": "건축법 제43조, 건축법 시행령 제27조의2, 지자체 건축조례",
            "법규기준": "대상 용도 및 규모 해당 여부 검토",
            "계획값": "데이터센터 세부 용도분류 확정 필요",
            "검토결과": "추가 검토필요",
        },
    ]
    return pd.DataFrame(rows)


def make_arch_summary(arch: Dict):
    rows = [
        ("용도", "방송통신시설/데이터센터"),
        ("층수", f"지하 {arch['basement_count']}층 / 지상 {arch['floor_count']}층 기준"),
        ("대지면적", fmt_area(arch["site_area"])),
        ("건축면적", fmt_area(arch["building_area"])),
        ("연면적", fmt_area(arch["far_area"])),
        ("건폐율", fmt_percent(arch["bcr"])),
        ("용적률", fmt_percent(arch["far"])),
        ("높이", f"{fmt_number(arch['height'], 1)} m"),
        ("층고 기준", arch["floor_height_note"]),
        ("주차대수", fmt_count(arch["parking_count"])),
        ("조경면적", fmt_area(arch["landscape_area"])),
    ]
    return pd.DataFrame(rows, columns=["항목", "계획"])


def make_floor_area_table(arch: Dict):
    rows = []
    for floor in arch["floor_plan"]:
        rows.append(
            {
                "층": floor["floor"],
                "주요 구성": floor["program"],
                "층별 면적": fmt_area(floor["area"]),
                "층고": f"{fmt_number(floor['height'], 1)} m",
            }
        )
    return pd.DataFrame(rows)


def metric_cards(items):
    html = ['<div class="metric-grid">']
    for label, value in items:
        html.append(
            f'<div class="metric-card"><div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_empty_result():
    st.markdown(
        '<div class="placeholder-box">주소가 입력되면 법규검토와 건축개요가 표시됩니다.</div>',
        unsafe_allow_html=True,
    )


left, right = st.columns([3, 7], gap="small")

with left:
    if os.path.exists("haeahn_logo.png"):
        st.image("haeahn_logo.png", width=132)
    st.markdown('<div class="app-title">HAEAHN PCM<br>Datacenter Solution</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">조건입력</div>', unsafe_allow_html=True)
    address = st.text_input("주소", placeholder="예: 서울특별시 금천구 디지털로10길 37")
    capacity_mw = st.number_input("규모 (MW)", min_value=0.5, max_value=300.0, value=20.0, step=0.5)
    dc_type = st.radio("유형", ["일반", "AI"], horizontal=True)
    operation_type = st.radio("운영방식", ["임대용", "자사용"], horizontal=True)
    run_review = st.button("검토 실행", type="primary", use_container_width=True)

    st.markdown('<div class="section-title">API 현황</div>', unsafe_allow_html=True)
    st.dataframe(api_status_df(), hide_index=True, use_container_width=True, height=250)

    cases = benchmark_summary()
    if cases:
        st.markdown('<div class="section-title">사례 데이터 기준값</div>', unsafe_allow_html=True)
        case_rows = []
        for name, stat in cases.items():
            case_rows.append(
                {
                    "항목": name,
                    "중앙값": fmt_number(stat["median"], 1),
                    "표본": stat["count"],
                }
            )
        st.dataframe(pd.DataFrame(case_rows), hide_index=True, use_container_width=True, height=210)

with right:
    tabs = st.tabs(["법규검토", "건축개요", "설비개요", "2D/3D"])

    address_info = {}
    building_info = {}
    land_info = {}
    arch = {}
    mep = {}
    should_review = run_review or bool(address)

    if should_review and address:
        with st.spinner("주소 및 공공 API 정보를 조회하는 중입니다."):
            address_info = kakao_search_address(address)
            building_info = get_building_register_info(address_info) if address_info else {}
            land_info = get_land_regulation_info(address_info) if address_info else {}
            arch = estimate_architecture(capacity_mw, dc_type, building_info, land_info)
            mep = estimate_mep(capacity_mw, dc_type, operation_type, arch)

    with tabs[0]:
        if not address:
            render_empty_result()
        else:
            site_address = address_info.get("jibun_address") or address_info.get("road_address") or address
            metric_cards(
                [
                    ("주소", site_address),
                    ("지역·지구", land_info.get("지역지구", "확인필요")),
                    ("정보출처", land_info.get("정보출처", "확인필요")),
                    ("검토 상태", "1차 검토"),
                ]
            )
            review_df = make_law_review(address_info, land_info, arch)
            st.dataframe(review_df, hide_index=True, use_container_width=True, height=430)
            if land_info.get("_error"):
                st.warning(f"토지이용규제 API: {land_info.get('_error')}")
            if building_info.get("_error"):
                st.info(f"건축물대장 API: {building_info.get('_error')}")

    with tabs[1]:
        if not address:
            render_empty_result()
        else:
            metric_cards(
                [
                    ("IT 용량", f"{fmt_number(capacity_mw, 1)} MW"),
                    ("예상 연면적", fmt_area(arch["far_area"])),
                    ("예상 랙 수", fmt_count(arch["rack_count"], "랙")),
                    ("기준 PUE", fmt_number(arch["pue"], 2)),
                ]
            )
            st.markdown('<div class="section-title">건축개요</div>', unsafe_allow_html=True)
            st.dataframe(make_arch_summary(arch), hide_index=True, use_container_width=True, height=420)
            st.markdown('<div class="section-title">스페이스 프로그램</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(arch["spaces"]), hide_index=True, use_container_width=True, height=420)
            st.markdown('<div class="section-title">층별 면적 계획</div>', unsafe_allow_html=True)
            st.dataframe(make_floor_area_table(arch), hide_index=True, use_container_width=True, height=360)

    with tabs[2]:
        if not address:
            render_empty_result()
        else:
            metric_cards(
                [
                    ("IT 부하", f"{fmt_number(capacity_mw * 1000, 1)} kW"),
                    ("총 시설부하", f"{fmt_number(arch['power_kw'], 1)} kW"),
                    ("예상 냉각부하", f"{fmt_number(arch['power_kw'] / 3.517, 1)} RT"),
                    ("평균 랙밀도", f"{fmt_number(arch['rack_kw'], 1)} kW/rack"),
                ]
            )
            st.markdown('<div class="section-title">설계 기준</div>', unsafe_allow_html=True)
            design_rows = [
                {"항목": "데이터센터 유형", "계획값": dc_type, "비고": "일반 / AI"},
                {"항목": "운영방식", "계획값": operation_type, "비고": "임대용 / 자사용"},
                {"항목": "목표 PUE", "계획값": fmt_number(arch["pue"], 2), "비고": "국내 사례 CSV 및 해외 사례 참고"},
                {"항목": "냉각 방식", "계획값": arch["cooling"], "비고": "유형별 기본 설정"},
                {"항목": "층별 주요 설비", "계획값": arch["floor_height_note"], "비고": "archi.md 반영"},
            ]
            st.dataframe(pd.DataFrame(design_rows), hide_index=True, use_container_width=True)

            st.markdown('<div class="section-title">전기 개요</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mep["electrical_rows"]), hide_index=True, use_container_width=True, height=390)

            st.markdown('<div class="section-title">기계 개요</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mep["mechanical_rows"]), hide_index=True, use_container_width=True, height=390)

            st.markdown('<div class="section-title">설비 면적 및 배치</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mep["space_rows"]), hide_index=True, use_container_width=True, height=180)
            st.dataframe(pd.DataFrame(mep["placement_rows"]), hide_index=True, use_container_width=True, height=170)
            st.dataframe(pd.DataFrame(mep["equipment_rows"]), hide_index=True, use_container_width=True, height=340)

            st.markdown('<div class="section-title">해외 사례 벤치마크</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(mep["benchmark_rows"]), hide_index=True, use_container_width=True, height=220)
            st.info("해외 사례는 Google 데이터센터 공식 효율/물관리 자료와 2025-2026 공개 액체냉각 연구를 기준으로 보수 적용했습니다.")

    with tabs[3]:
        st.markdown(
            '<div class="placeholder-box">2D/3D 배치와 평면은 2단계 개발 범위입니다. '
            "향후 V-World 경계, 주변 도로, 건축물대장 정보를 결합해 배치도와 층별 평면을 생성합니다.</div>",
            unsafe_allow_html=True,
        )
