import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()


@dataclass
class ApiStatus:
    name: str
    key: Optional[str]
    active: bool


def get_api_status() -> list[ApiStatus]:
    return [
        ApiStatus("건축물대장정보 API", BUILDING_API_KEY, bool(BUILDING_API_KEY)),
        ApiStatus("토지이용규제 API", LAND_REGULATION_API_KEY, bool(LAND_REGULATION_API_KEY)),
        ApiStatus("V-world API", VWORLD_API_KEY, bool(VWORLD_API_KEY)),
        ApiStatus("카카오맵 JS API", KAKAO_MAP_API_KEY, bool(KAKAO_MAP_API_KEY)),
        ApiStatus("카카오맵 REST API", KAKAO_REST_API_KEY, bool(KAKAO_REST_API_KEY)),
    ]


def _safe_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def _safe_float(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def _is_ascii_text(value: object) -> bool:
    try:
        str(value).encode("ascii")
        return True
    except (UnicodeEncodeError, TypeError):
        return False


def _sanitize_api_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip()
    return key if key and _is_ascii_text(key) else None


BUILDING_API_KEY = _sanitize_api_key(os.getenv("BUILDING_API_KEY"))
LAND_REGULATION_API_KEY = _sanitize_api_key(os.getenv("LAND_REGULATION_API_KEY"))
VWORLD_API_KEY = _sanitize_api_key(os.getenv("VWORLD_API_KEY"))
KAKAO_MAP_API_KEY = _sanitize_api_key(os.getenv("KAKAO_MAP_API_KEY"))
KAKAO_REST_API_KEY = _sanitize_api_key(os.getenv("KAKAO_REST_API_KEY"))


def parse_lot_number(address_text: str) -> tuple[Optional[str], Optional[str]]:
    if not address_text:
        return None, None
    text = address_text.strip()
    match = re.search(r"(\d{1,5})[-‐‑–](\d{1,5})\s*$", text)
    if match:
        return match.group(1).zfill(4), match.group(2).zfill(4)
    match = re.search(r"(\d{1,5})\s*$", text)
    if match:
        return match.group(1).zfill(4), "0000"
    return None, None


def get_kakao_address_data(address: str) -> Optional[dict]:
    if not address or not KAKAO_REST_API_KEY:
        return None
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers={"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"},
            params={"query": address, "size": 5},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        documents = data.get("documents") or []
        return documents[0] if documents else None
    except (requests.RequestException, UnicodeEncodeError):
        return None


def extract_building_query_params(kakao_result: dict) -> Optional[dict]:
    if not kakao_result:
        return None
    address = kakao_result.get("address") or {}
    road_address = kakao_result.get("road_address") or {}
    b_code = address.get("b_code") or road_address.get("b_code")
    if not b_code or len(b_code) < 10:
        return None
    sigunguCd = b_code[:5]
    bjdongCd = b_code[5:10]
    address_name = address.get("address_name") or road_address.get("address_name") or kakao_result.get("address_name")
    bun, ji = parse_lot_number(address_name)
    params = {
        "sigunguCd": sigunguCd,
        "bjdongCd": bjdongCd,
        "platGbCd": "0",
        "bun": bun,
        "ji": ji,
    }
    return {k: v for k, v in params.items() if v is not None}


def _call_building_register_api(endpoint: str, params: dict) -> list[dict]:
    query = {
        "serviceKey": BUILDING_API_KEY,
        "_type": "json",
        "numOfRows": "10",
        "pageNo": "1",
        **params,
    }
    try:
        response = requests.get(
            f"https://apis.data.go.kr/1613000/BldRgstHubService/{endpoint}",
            params=query,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        body = data.get("response", {}).get("body", {})
        items = body.get("items") or {}
        if not items:
            return []
        item = items.get("item")
        if item is None:
            return []
        return item if isinstance(item, list) else [item]
    except requests.RequestException:
        return []
    except ValueError:
        return []


def get_building_register_item(address: str) -> Optional[dict]:
    kakao_result = get_kakao_address_data(address)
    if not kakao_result:
        return None
    query_params = extract_building_query_params(kakao_result)
    if not query_params:
        return None

    for endpoint in ["getBrTitleInfo", "getBrRecapTitleInfo"]:
        items = _call_building_register_api(endpoint, query_params)
        if items:
            return items[0]
    return None


def parse_region(address: str) -> str:
    if not address:
        return "주소 미입력 - 기본 지역 정보 없음"
    if "서울" in address:
        return "서울특별시"
    if "강남" in address or "서초" in address:
        return "서울특별시 강남구"
    if "성남" in address:
        return "경기도 성남시"
    if "부산" in address:
        return "부산광역시"
    return "지정되지 않은 지역"


def get_region_district(address: str) -> tuple[str, str]:
    region = parse_region(address)
    district = "일반공업지역 / 제2종근린생활시설"
    if "서울" in region:
        district = "제2종일반주거지역 / 산업시설지구(데이터센터 가능)"
    return region, district


def compute_building_overview_local(address: str, scale_mw: float, center_type: str) -> Dict[str, object]:
    scale_mw = max(scale_mw, 0.1)
    site_factor = 5200 if center_type == "AI 데이터센터" else 4500
    site_area = round(scale_mw * site_factor)
    coverage_rate = 45 if center_type == "AI 데이터센터" else 42
    coverage_building_area = round(site_area * coverage_rate / 100)
    floors = 5 if scale_mw >= 5 else 4 if scale_mw >= 2 else 3
    floor_height = 6.0
    gross_floor_area = round(coverage_building_area * floors)
    total_height = round(floors * floor_height + 3, 1)
    floor_area = round(gross_floor_area / floors)
    far = round(gross_floor_area / site_area, 2)
    parking = max(10, round(gross_floor_area / 400))
    landscaping_area = round(site_area * 0.12)
    region, district = get_region_district(address)
    address_display = address if address else "미입력"
    region_district_display = f"{region} / {district}" if address else "미입력"
    return {
        "주소": address_display,
        "지역/지구": region_district_display,
        "대지면적 (㎡)": site_area,
        "예상 연면적 (㎡)": gross_floor_area,
        "예상 건축면적 (㎡)": coverage_building_area,
        "건폐율 (%)": coverage_rate,
        "용적률": far,
        "예상높이 (m)": total_height,
        "층수": floors,
        "층고 (m)": floor_height,
        "주차대수": parking,
        "조경면적 (㎡)": landscaping_area,
        "층별평균면적 (㎡)": floor_area,
        "데이터센터유형": center_type,
        "예상전력규모 (MW)": scale_mw,
    }


def compute_building_overview(address: str, scale_mw: float, center_type: str) -> Dict[str, object]:
    local_overview = compute_building_overview_local(address, scale_mw, center_type)
    api_item = get_building_register_item(address)
    if not api_item:
        return local_overview

    site_area = _safe_float(api_item.get("platArea"))
    if not site_area:
        site_area = local_overview["대지면적 (㎡)"]
    gross_floor_area = _safe_float(api_item.get("totArea") or api_item.get("archArea"))
    if not gross_floor_area:
        gross_floor_area = local_overview["예상 연면적 (㎡)"]
    coverage_rate = _safe_float(api_item.get("bcRat"))
    if not coverage_rate:
        coverage_rate = local_overview["건폐율 (%)"]
    coverage_building_area = round(site_area * coverage_rate / 100) if site_area else local_overview["예상 건축면적 (㎡)"]
    vl_rate = _safe_float(api_item.get("vlRat"))
    if vl_rate is None or vl_rate == 0:
        far = local_overview["용적률"]
    elif vl_rate > 10:
        far = round(vl_rate / 100, 2)
    else:
        far = round(vl_rate, 2)
    total_height = _safe_float(api_item.get("heit"))
    if not total_height:
        total_height = local_overview["예상높이 (m)"]
    grnd = _safe_int(api_item.get("grndFlrCnt"), 0) or 0
    ugrnd = _safe_int(api_item.get("ugrndFlrCnt"), 0) or 0
    floors = grnd + ugrnd if grnd + ugrnd > 0 else local_overview["층수"]
    parking = _safe_int(api_item.get("totPkngCnt"), local_overview["주차대수"])
    if parking is None:
        parking = local_overview["주차대수"]
    landscaping_area = local_overview["조경면적 (㎡)"]
    if site_area and site_area > 0:
        landscaping_area = round(site_area * 0.12)
    floor_area = round(gross_floor_area / floors) if floors else local_overview["층별평균면적 (㎡)"]

    region_name = api_item.get("jiyukCdNm") or api_item.get("jiguCdNm") or local_overview["지역/지구"]
    district_name = api_item.get("jiguCdNm") or local_overview["지역/지구"]
    region_district_display = f"{region_name} / {district_name}" if address else "미입력"
    if not api_item.get("jiyukCdNm") and not api_item.get("jiguCdNm"):
        region_district_display = local_overview["지역/지구"]

    return {
        "주소": address if address else "미입력",
        "지역/지구": region_district_display,
        "대지면적 (㎡)": site_area,
        "예상 연면적 (㎡)": gross_floor_area,
        "예상 건축면적 (㎡)": coverage_building_area,
        "건폐율 (%)": coverage_rate,
        "용적률": far,
        "예상높이 (m)": total_height,
        "층수": floors,
        "층고 (m)": local_overview["층고 (m)"],
        "주차대수": parking,
        "조경면적 (㎡)": landscaping_area,
        "층별평균면적 (㎡)": floor_area,
        "데이터센터유형": center_type,
        "예상전력규모 (MW)": scale_mw,
    }


def format_overview_value(key: str, value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value

    if key in ["대지면적 (㎡)", "예상 연면적 (㎡)", "예상 건축면적 (㎡)", "조경면적 (㎡)", "층별평균면적 (㎡)"]:
        return f"{int(value):,} ㎡"
    if key in ["예상높이 (m)", "층고 (m)"]:
        return f"{value:,} m" if isinstance(value, int) else f"{value:,.1f} m"
    if key == "건폐율 (%)":
        return f"{value:,.0f}%"
    if key == "용적률":
        return f"{value * 100:,.0f}%"
    if key == "예상전력규모 (MW)":
        return f"{value:,.1f} MW" if isinstance(value, float) else f"{value:,} MW"
    if key == "주차대수":
        return f"{int(value):,} 대"
    if key == "층수":
        return f"{int(value):,} 층"
    return str(value)


def compute_law_review(address: str, overview: dict) -> tuple[str, pd.DataFrame]:
    region, district = get_region_district(address)
    planned_coverage = overview["건폐율 (%)"]
    planned_far = overview["용적률"]
    site_area = overview["대지면적 (㎡)"]
    building_area = overview["예상 연면적 (㎡)"]
    planned_landscape_rate = round(overview["조경면적 (㎡)"] / site_area * 100, 1)
    required_parking = max(10, int(overview["예상전력규모 (MW)"] * 4 + 10))
    sunlight = "정북일조선 적용 - 높이 24m 이하로 제한 해제 가능"
    if overview["예상높이 (m)"] > 24:
        sunlight = "정북일조선 적용 대상"
    law_rows = [
        ["법정건폐율", "건축법 제42조, 건축물의 건폐율 60% 이하", f"{planned_coverage}%", "적합" if planned_coverage <= 60 else "불합격"],
        ["법정용적률", "건축법 제43조, 용적률 200% 이하", f"{planned_far * 100:.0f}%", "적합" if planned_far <= 2.0 else "불합격"],
        ["법정주차대수", "건축법 시행령 제61조 및 건축물의 주차장 설치기준", f"{required_parking}대", "적합"],
        ["대지안의 공지", "건축법 제44조, 인접대지경계선 3m 이상 확보 권장", "3m 이상 확보", "검토 필요"],
        ["일조사선", "건축법 제58조, 일조사선에 따른 높이 제한 검토", sunlight, "해당"],
        ["지역지구 제한", "국토의 계획 및 이용에 관한 법률 제7조 및 건축법 제4조", district, "검토 필요"],
        ["법정조경률", "국토의 계획 및 이용에 관한 법률 제57조, 조경률 10% 이상", f"{planned_landscape_rate}%", "적합" if planned_landscape_rate >= 10 else "불합격"],
        ["공개공지", "건축법 제50조, 공개공지 대상 여부 확인", "해당없음", "해당없음"],
    ]
    df = pd.DataFrame(law_rows, columns=["법규항목", "법규조항/기준", "계획값", "검토결과"])
    header = f"지역/지구: {region}  |  용도: 데이터센터"
    return header, df


def compute_mep_overview(overview: dict) -> pd.DataFrame:
    total_building_area = overview["예상 연면적 (㎡)"]
    it_area = round(total_building_area * 0.35)
    hh_area = round(total_building_area * 0.12)
    mech_area = round(total_building_area * 0.15)
    support_area = round(total_building_area * 0.08)
    infra_area = total_building_area - it_area - hh_area - mech_area - support_area
    rack_power_density = 40 if overview["데이터센터유형"] == "AI 데이터센터" else 35
    rack_count = int(overview["예상전력규모 (MW)"] * 1000 / rack_power_density)
    ups_capacity = int(overview["예상전력규모 (MW)"] * 1200)
    water_supply = int(overview["예상전력규모 (MW)"] * 12)
    power_demand = int(overview["예상전력규모 (MW)"] * 1000)
    available_service_capacity = int(power_demand * 1.25)
    cooling_load_rt = round(power_demand * 0.35 / 3.517, 1)
    rows = [
        ["전산실 면적", f"{it_area:,} ㎡"],
        ["항온항습실 면적", f"{hh_area:,} ㎡"],
        ["전산기계실 면적", f"{mech_area:,} ㎡"],
        ["기반시설 면적", f"{infra_area:,} ㎡"],
        ["지원시설 면적", f"{support_area:,} ㎡"],
        ["UPS 용량", f"{ups_capacity:,} kVA"],
        ["랙 수량", f"{rack_count:,} EA"],
        ["랙 전력 밀도", f"{rack_power_density:,} kW/rack"],
        ["필요 수전 용량", f"{power_demand:,} kW"],
        ["확보 가능한 수전 용량", f"{available_service_capacity:,} kW"],
        ["예상 냉각부하", f"{cooling_load_rt:,} RT"],
        ["상수도 공급량", f"{water_supply:,} m³/day"],
    ]
    return pd.DataFrame(rows, columns=["항목", "예상값"])


def compute_archi_space_program(overview: dict) -> pd.DataFrame:
    floors = overview["층수"]
    floor_area = overview["층별평균면적 (㎡)"]
    distribution = {
        "전산실": 0.35,
        "항온항습실": 0.12,
        "전산기계실": 0.15,
        "기반시설": 0.18,
        "지원시설": 0.10,
        "기타": 0.10,
    }
    rows = []
    for level in range(1, floors + 1):
        row = {"층": f"{level}층"}
        for key, ratio in distribution.items():
            area = round(floor_area * ratio)
            row[f"{key} 면적 (㎡)"] = f"{area:,} ㎡"
            row[f"{key} 비율 (%)"] = f"{int(ratio * 100):,}%"
        row["총면적 (㎡)"] = f"{int(floor_area):,} ㎡"
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title="HAEAHN PCM Datacenter Solution", layout="wide")

    st.markdown("""
        <style>
        [data-testid="stVerticalBlock"] {
            gap: 0;
        }
        </style>
    """, unsafe_allow_html=True)

    left, right = st.columns([3, 7], gap="small")

    with left:
        st.image("haeahn logo.png", width=170)
        st.markdown("### HAEAHN PCM Datacenter Solution")
        st.divider()

        # 조건 입력 컨테이너 (위)
        with st.container():
            st.subheader("조건 입력")
            address = st.text_input("주소 입력", value="")
            scale_mw = st.number_input("규모 (MW)", min_value=0.1, max_value=100.0, value=3.0, step=0.1)
            center_type = st.radio("데이터센터 유형", ["일반 데이터센터", "AI 데이터센터"])
            st.caption("주소와 MW를 입력하면 건축개요, 법규검토, 설비개요를 자동으로 계산합니다.")

        st.divider()

        # API 연결 현황 컨테이너 (아래)
        with st.container(border=True):
            st.subheader("API 연결 현황")
            api_status = get_api_status()
            status_table = pd.DataFrame(
                [[api.name, "연결됨" if api.active else "키 없음"] for api in api_status],
                columns=["서비스", "상태"],
            )
            st.table(status_table)

    with right:
        st.markdown("""
            <style>
            .stTabs [data-baseweb="tabs"] button [data-testid="stMarkdownContainer"] p {
                font-size: 22px;
                font-weight: 600;
                color: #555555;
            }
            .stTabs [data-baseweb="tabs"] {
                background-color: #d9dde6;
            }
            </style>
        """, unsafe_allow_html=True)
        
        tabs = st.tabs(["건축개요", "법규검토", "설비개요", "2D/3D"])

        overview = compute_building_overview(address, scale_mw, center_type)
        law_header, law_df = compute_law_review(address, overview)
        mep_df = compute_mep_overview(overview)

        with tabs[0]:
            st.markdown("### 건축개요")
            st.write("데이터센터 전용 건축개요를 빠르게 파악할 수 있습니다.")
            overview_display = {key: format_overview_value(key, value) for key, value in overview.items()}
            st.table(pd.DataFrame([overview_display]).T.rename(columns={0: "값"}))

            st.markdown("#### 층별 스페이스 프로그램")
            archi_df = compute_archi_space_program(overview)
            st.table(archi_df.reset_index(drop=True).to_dict("records"))
            st.caption("archi.md 기준의 층별 스페이스 프로그램과 면적/비율입니다.")
            st.info("전산시설, 기반시설, 지원시설을 포함한 데이터센터 기초 설계 정보입니다.")

        with tabs[1]:
            st.markdown("### 법규검토")
            st.write(law_header)
            st.write(law_df)
            st.caption("주소가 없는 경우 기본 법규 기준을 사용하여 예측 검토합니다.")

        with tabs[2]:
            st.markdown("### 설비개요")
            st.write("전체 설비 면적 및 MEP 주요 지표를 요약합니다.")
            st.table(mep_df)
            st.info("UPS, 랙 수, 수전 용량과 냉각부하를 포함한 설비 검토 결과입니다.")

        with tabs[3]:
            st.markdown("### 2D/3D 도면(준비중)")
            st.warning("2단계에서 배치도와 3D 도면 표기를 구현합니다.")
            st.write(
                "현재 1단계에서는 건축개요, 법규검토, 설비개요를 우선적으로 완성하였습니다."
            )

    st.divider()
    st.markdown(
        "---\n" 
        "#### 참고: 현재 프로토타입은 주소/규모 입력을 바탕으로 자동 설계 요약을 제공합니다.\n"
        "*.env 파일의 API 키를 읽어와 상태를 확인하며, 실제 API 연결은 추후 단계에서 추가 구현됩니다.*"
    )


if __name__ == "__main__":
    main()
