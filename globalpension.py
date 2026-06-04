"""
globalpension.py  –  Streamlit 웹 대시보드
실행: streamlit run globalpension.py
"""

import streamlit as st
import pandas as pd

# ══════════════════════════════════════════════════════════════
# 데이터
# ══════════════════════════════════════════════════════════════

ALLOCATION_DETAIL = [
    {"fund":"CPP Investments","year":"FY2025","aum":714.4,"currency":"CAD B",
     "주식 합계":0.58,"상장주식":0.29,"사모주식":0.29,
     "채권/FI":0.15,"부동산":0.07,"인프라":0.09,
     "크레딧":0.11,"대체투자":None,"현금/기타":None,
     "notes":"Real Estate + Infra 별도 집계"},
    {"fund":"CPP Investments","year":"FY2026","aum":793.3,"currency":"CAD B",
     "주식 합계":0.58,"상장주식":0.36,"사모주식":0.22,
     "채권/FI":0.13,"부동산":None,"인프라":None,
     "크레딧":0.09,"대체투자":None,"현금/기타":None,
     "notes":"FY2026부터 Real Assets 통합 20%"},
    {"fund":"OTPP","year":"2024","aum":266.3,"currency":"CAD B",
     "주식 합계":0.41,"상장주식":0.14,"사모주식":0.23,
     "채권/FI":0.30,"부동산":0.11,"인프라":0.17,
     "크레딧":0.14,"대체투자":0.09,"현금/기타":None,
     "notes":"ARS(절대수익) 9% 별도"},
    {"fund":"OTPP","year":"2025","aum":279.4,"currency":"CAD B",
     "주식 합계":0.43,"상장주식":0.18,"사모주식":0.19,
     "채권/FI":0.23,"부동산":0.10,"인프라":0.13,
     "크레딧":0.14,"대체투자":0.09,"현금/기타":0.20,
     "notes":"Venture Growth 6% 포함; 인플레이션민감 20%"},
    {"fund":"PSP Investments","year":"FY2024","aum":264.9,"currency":"CAD B",
     "주식 합계":None,"상장주식":0.21,"사모주식":0.153,
     "채권/FI":0.212,"부동산":0.103,"인프라":0.130,
     "크레딧":0.099,"대체투자":None,"현금/기타":0.066,
     "notes":"자연자원 6.6% 포함"},
    {"fund":"PSP Investments","year":"FY2025","aum":299.7,"currency":"CAD B",
     "주식 합계":None,"상장주식":None,"사모주식":0.136,
     "채권/FI":None,"부동산":0.089,"인프라":0.107,
     "크레딧":0.101,"대체투자":None,"현금/기타":0.077,
     "notes":"Capital Markets 48.7%; 자연자원 6.0%"},
    {"fund":"NZ Super Fund","year":"FY2024","aum":76.65,"currency":"NZD B",
     "주식 합계":0.50,"상장주식":0.46,"사모주식":0.03,
     "채권/FI":0.21,"부동산":0.05,"인프라":0.05,
     "크레딧":None,"대체투자":0.07,"현금/기타":0.13,
     "notes":"Rural/Timber 5% 포함"},
    {"fund":"NZ Super Fund","year":"FY2025","aum":85.1,"currency":"NZD B",
     "주식 합계":0.54,"상장주식":0.50,"사모주식":0.05,
     "채권/FI":0.18,"부동산":0.05,"인프라":0.04,
     "크레딧":None,"대체투자":0.08,"현금/기타":0.11,
     "notes":"Rural/Timber 5% 포함"},
    {"fund":"CDPQ","year":"2024","aum":473.3,"currency":"CAD B",
     "주식 합계":0.466,"상장주식":0.275,"사모주식":0.191,
     "채권/FI":0.328,"부동산":0.089,"인프라":0.136,
     "크레딧":0.217,"대체투자":None,"현금/기타":0.009,
     "notes":"Rates 10.3% + Credit 21.7% = FI 32.8%"},
    {"fund":"CDPQ (La Caisse)","year":"2025","aum":517.3,"currency":"CAD B",
     "주식 합계":0.456,"상장주식":0.292,"사모주식":0.164,
     "채권/FI":0.341,"부동산":0.083,"인프라":0.144,
     "크레딧":0.233,"대체투자":None,"현금/기타":0.011,
     "notes":"Rates 10.2% + Credit 23.3% = FI 34.1%"},
    {"fund":"Future Fund","year":"FY2024","aum":224.9,"currency":"AUD B",
     "주식 합계":0.373,"상장주식":0.270,"사모주식":0.145,
     "채권/FI":None,"부동산":0.054,"인프라":0.099,
     "크레딧":0.110,"대체투자":0.152,"현금/기타":0.067,
     "notes":"호주 주식 10.3% 포함"},
    {"fund":"Future Fund","year":"FY2025","aum":252.3,"currency":"AUD B",
     "주식 합계":0.423,"상장주식":0.325,"사모주식":0.133,
     "채권/FI":None,"부동산":0.044,"인프라":0.114,
     "크레딧":0.089,"대체투자":0.147,"현금/기타":0.051,
     "notes":"호주 주식 10.8% 포함"},
    {"fund":"GPFG (Norway)","year":"2024","aum":19742,"currency":"NOK B",
     "주식 합계":0.714,"상장주식":0.714,"사모주식":None,
     "채권/FI":0.266,"부동산":0.018,"인프라":0.001,
     "크레딧":None,"대체투자":None,"현금/기타":0.002,
     "notes":"비상장 RE 1.8%; 상장 RE 별도"},
    {"fund":"GPFG (Norway)","year":"2025","aum":21268,"currency":"NOK B",
     "주식 합계":0.713,"상장주식":0.713,"사모주식":None,
     "채권/FI":0.265,"부동산":0.017,"인프라":0.004,
     "크레딧":None,"대체투자":None,"현금/기타":0.004,
     "notes":"인프라 3배 증가 (태양광·풍력)"},
    {"fund":"CalPERS","year":"FY2025","aum":634.6,"currency":"USD B",
     "주식 합계":0.393,"상장주식":0.258,"사모주식":0.156,
     "채권/FI":0.270,"부동산":0.074,"인프라":0.033,
     "크레딧":None,"대체투자":None,"현금/기타":0.034,
     "notes":"민간부채 3.4% 포함"},
]

GEOGRAPHIC_EXPOSURE = [
    {"fund":"CPP Investments","year":"FY2025",
     "미국":0.47,"캐나다":0.12,"유럽":0.19,"아시아태평양":0.17,"중남미":0.05,"호주":None,"기타/EM":None,"북미 전체":None,"뉴질랜드":None,
     "notes":"5개년 US 36→36→38→42→47%"},
    {"fund":"CPP Investments","year":"FY2026",
     "미국":0.48,"캐나다":0.12,"유럽":0.17,"아시아태평양":0.18,"중남미":0.05,"호주":None,"기타/EM":None,"북미 전체":None,"뉴질랜드":None,
     "notes":"비캐나다 비중 78%"},
    {"fund":"OTPP","year":"2025",
     "미국":0.38,"캐나다":0.31,"유럽":0.18,"아시아태평양":0.08,"중남미":0.05,"호주":None,"기타/EM":None,"북미 전체":None,"뉴질랜드":None,
     "notes":"USD $117B, EMEA $56B, APAC $26B, LatAm $17B"},
    {"fund":"PSP Investments","year":"FY2025",
     "미국":0.405,"캐나다":0.200,"유럽":0.163,"아시아태평양":0.113,"중남미":None,"호주":0.055,"기타/EM":0.064,"북미 전체":None,"뉴질랜드":None,
     "notes":"Oceania 5.5% 포함"},
    {"fund":"NZ Super Fund","year":"FY2024",
     "미국":None,"캐나다":None,"유럽":0.196,"아시아태평양":0.079,"중남미":None,"호주":0.038,"기타/EM":0.040,"북미 전체":0.541,"뉴질랜드":0.106,
     "notes":"Japan 4.2% 포함"},
    {"fund":"NZ Super Fund","year":"FY2025",
     "미국":None,"캐나다":None,"유럽":0.181,"아시아태평양":0.081,"중남미":None,"호주":0.024,"기타/EM":0.030,"북미 전체":0.571,"뉴질랜드":0.113,
     "notes":"Japan 3.5% 포함"},
    {"fund":"CDPQ","year":"2024",
     "미국":0.38,"캐나다":0.30,"유럽":0.15,"아시아태평양":0.10,"중남미":0.04,"호주":None,"기타/EM":0.03,"북미 전체":None,"뉴질랜드":None,
     "notes":"65개국 이상 투자"},
    {"fund":"CDPQ (La Caisse)","year":"2025",
     "미국":0.38,"캐나다":0.29,"유럽":0.17,"아시아태평양":0.10,"중남미":0.04,"호주":None,"기타/EM":0.02,"북미 전체":None,"뉴질랜드":None,
     "notes":"퀘벡 자산 $100B 달성"},
    {"fund":"Future Fund","year":"FY2024",
     "미국":0.43,"캐나다":None,"유럽":0.15,"아시아태평양":0.06,"중남미":None,"호주":0.21,"기타/EM":0.10,"북미 전체":None,"뉴질랜드":None,
     "notes":"물리적 소재지 기준; EM 10%"},
    {"fund":"Future Fund","year":"FY2025",
     "미국":0.43,"캐나다":None,"유럽":0.15,"아시아태평양":0.06,"중남미":None,"호주":0.23,"기타/EM":0.10,"북미 전체":None,"뉴질랜드":None,
     "notes":"물리적 소재지 기준; EM 10%"},
    {"fund":"GPFG (Norway)","year":"2024",
     "미국":0.534,"캐나다":None,"유럽":0.252,"아시아태평양":0.142,"중남미":0.005,"호주":0.020,"기타/EM":0.007,"북미 전체":0.569,"뉴질랜드":None,
     "notes":"중동 0.4%, 아프리카 0.3%"},
    {"fund":"GPFG (Norway)","year":"2025",
     "미국":0.529,"캐나다":None,"유럽":0.258,"아시아태평양":0.145,"중남미":0.005,"호주":0.019,"기타/EM":0.008,"북미 전체":0.560,"뉴질랜드":None,
     "notes":"중동 0.4%, 아프리카 0.4%"},
    {"fund":"CalPERS","year":"FY2025",
     "미국":None,"캐나다":None,"유럽":None,"아시아태평양":None,"중남미":None,"호주":None,"기타/EM":None,"북미 전체":None,"뉴질랜드":None,
     "notes":"국내 $163.8B / 해외주식 $79.7B (세부 지역 미공개)"},
]

RETURNS_BY_ASSET_CLASS = [
    {"fund":"CPP Investments","year":"FY2025",
     "총 펀드":0.093,"상장주식":0.106,"사모주식":0.118,"채권/FI":0.081,
     "부동산":0.038,"인프라":0.094,"크레딧":0.144,"대체투자":None,"실물자산":None,
     "notes":"Credit +14.4%; RE +3.8%"},
    {"fund":"CPP Investments","year":"FY2026",
     "총 펀드":0.078,"상장주식":0.175,"사모주식":0.029,"채권/FI":-0.001,
     "부동산":0.037,"인프라":0.112,"크레딧":0.037,"대체투자":None,"실물자산":0.122,
     "notes":"Sust.Energy +23.2%; Infra +11.2%"},
    {"fund":"OTPP","year":"2025",
     "총 펀드":0.067,"상장주식":0.150,"사모주식":-0.053,"채권/FI":0.026,
     "부동산":-0.031,"인프라":0.018,"크레딧":0.058,"대체투자":None,"실물자산":-0.004,
     "notes":"Venture Growth +30.2%; 벤치마크 대비 -5.0%"},
    {"fund":"PSP Investments","year":"FY2024",
     "총 펀드":0.072,"상장주식":0.175,"사모주식":0.121,"채권/FI":0.029,
     "부동산":-0.159,"인프라":0.143,"크레딧":0.142,"대체투자":None,"실물자산":None,
     "notes":"RE -15.9% (오피스 평가손)"},
    {"fund":"PSP Investments","year":"FY2025",
     "총 펀드":0.126,"상장주식":None,"사모주식":None,"채권/FI":None,
     "부동산":None,"인프라":None,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"하이라이트만 공개; 5yr 10.6%, 10yr 8.2%"},
    {"fund":"NZ Super Fund","year":"FY2024",
     "총 펀드":0.149,"상장주식":None,"사모주식":None,"채권/FI":None,
     "부동산":None,"인프라":None,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"Reference Portfolio 15.13%; Value add -0.24%"},
    {"fund":"NZ Super Fund","year":"FY2025",
     "총 펀드":0.1184,"상장주식":None,"사모주식":None,"채권/FI":None,
     "부동산":None,"인프라":None,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"Reference Portfolio 10.87%; Value add +0.98%"},
    {"fund":"CDPQ","year":"2024",
     "총 펀드":0.094,"상장주식":0.255,"사모주식":0.172,"채권/FI":0.018,
     "부동산":-0.108,"인프라":0.095,"크레딧":0.008,"대체투자":None,"실물자산":None,
     "notes":"RE -10.8%; 5yr 6.2%"},
    {"fund":"CDPQ (La Caisse)","year":"2025",
     "총 펀드":0.093,"상장주식":0.177,"사모주식":0.023,"채권/FI":0.005,
     "부동산":0.002,"인프라":0.092,"크레딧":0.096,"대체투자":None,"실물자산":None,
     "notes":"Credit +9.6%; Infra +9.2%"},
    {"fund":"Future Fund","year":"FY2024",
     "총 펀드":0.091,"상장주식":None,"사모주식":None,"채권/FI":None,
     "부동산":None,"인프라":None,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"자산군별 수익률 미공개"},
    {"fund":"Future Fund","year":"FY2025",
     "총 펀드":0.122,"상장주식":None,"사모주식":None,"채권/FI":None,
     "부동산":None,"인프라":None,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"자산군별 수익률 미공개"},
    {"fund":"GPFG (Norway)","year":"2024",
     "총 펀드":0.1309,"상장주식":0.1819,"사모주식":None,"채권/FI":0.0128,
     "부동산":-0.0057,"인프라":-0.0981,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"펀드 통화 바스켓 기준; Infra -9.81%"},
    {"fund":"GPFG (Norway)","year":"2025",
     "총 펀드":0.1511,"상장주식":0.1929,"사모주식":None,"채권/FI":0.0542,
     "부동산":0.0436,"인프라":0.1807,"크레딧":None,"대체투자":None,"실물자산":None,
     "notes":"펀드 통화 바스켓 기준; Infra +18.07%"},
    {"fund":"CalPERS","year":"FY2025",
     "총 펀드":0.116,"상장주식":0.168,"사모주식":0.143,"채권/FI":0.065,
     "부동산":0.028,"인프라":None,"크레딧":0.128,"대체투자":None,"실물자산":None,
     "notes":"PE는 Mar 2025 기준; 벤치마크 +1.7%p 초과"},
]

MULTI_YEAR_RETURNS = [
    {"fund":"CPP Investments","year":"FY2026","currency":"CAD","1년(최신)":0.078,"1년(전년)":0.093,"5년(연환)":0.066,"10년(연환)":0.088,"설정이후":None,"FY종료":"Mar 31"},
    {"fund":"CPP Investments","year":"FY2025","currency":"CAD","1년(최신)":0.093,"1년(전년)":0.080,"5년(연환)":0.090,"10년(연환)":0.083,"설정이후":None,"FY종료":"Mar 31"},
    {"fund":"OTPP","year":"2025","currency":"CAD","1년(최신)":0.067,"1년(전년)":0.094,"5년(연환)":0.066,"10년(연환)":0.068,"설정이후":0.092,"FY종료":"Dec 31"},
    {"fund":"PSP Investments","year":"FY2025","currency":"CAD","1년(최신)":0.126,"1년(전년)":0.072,"5년(연환)":0.106,"10년(연환)":0.082,"설정이후":None,"FY종료":"Mar 31"},
    {"fund":"PSP Investments","year":"FY2024","currency":"CAD","1년(최신)":0.072,"1년(전년)":None,"5년(연환)":0.079,"10년(연환)":0.083,"설정이후":None,"FY종료":"Mar 31"},
    {"fund":"NZ Super Fund","year":"FY2025","currency":"NZD","1년(최신)":0.1184,"1년(전년)":0.149,"5년(연환)":0.1162,"10년(연환)":0.1006,"설정이후":0.1009,"FY종료":"Jun 30"},
    {"fund":"NZ Super Fund","year":"FY2024","currency":"NZD","1년(최신)":0.149,"1년(전년)":0.126,"5년(연환)":0.0952,"10년(연환)":0.1033,"설정이후":0.1000,"FY종료":"Jun 30"},
    {"fund":"CDPQ","year":"2025","currency":"CAD","1년(최신)":0.093,"1년(전년)":0.094,"5년(연환)":0.065,"10년(연환)":0.072,"설정이후":None,"FY종료":"Dec 31"},
    {"fund":"CDPQ","year":"2024","currency":"CAD","1년(최신)":0.094,"1년(전년)":0.072,"5년(연환)":0.062,"10년(연환)":0.071,"설정이후":None,"FY종료":"Dec 31"},
    {"fund":"Future Fund","year":"FY2025","currency":"AUD","1년(최신)":0.122,"1년(전년)":0.091,"5년(연환)":0.094,"10년(연환)":0.080,"설정이후":0.079,"FY종료":"Jun 30"},
    {"fund":"Future Fund","year":"FY2024","currency":"AUD","1년(최신)":0.091,"1년(전년)":0.082,"5년(연환)":0.067,"10년(연환)":0.083,"설정이후":0.077,"FY종료":"Jun 30"},
    {"fund":"GPFG (Norway)","year":"2025","currency":"NOK","1년(최신)":0.1511,"1년(전년)":0.1309,"5년(연환)":0.0826,"10년(연환)":0.0847,"설정이후":0.0664,"FY종료":"Dec 31"},
    {"fund":"GPFG (Norway)","year":"2024","currency":"NOK","1년(최신)":0.1309,"1년(전년)":0.1614,"5년(연환)":0.0744,"10년(연환)":0.0725,"설정이후":0.0634,"FY종료":"Dec 31"},
    {"fund":"CalPERS","year":"FY2025","currency":"USD","1년(최신)":0.116,"1년(전년)":None,"5년(연환)":0.080,"10년(연환)":0.071,"설정이후":None,"FY종료":"Jun 30"},
]

FUNDS = sorted(set(r["fund"] for r in ALLOCATION_DETAIL))

# ══════════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════════

def to_pct_df(records, value_cols, key_cols=("fund","year")):
    """dict 리스트 → DataFrame, 수치열을 % 포맷으로"""
    rows = []
    for r in records:
        row = {k: r.get(k) for k in list(key_cols) + value_cols + ["notes"]}
        rows.append(row)
    df = pd.DataFrame(rows)
    for c in value_cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: f"{v*100:.1f}%" if pd.notna(v) and v is not None else "–")
    return df

def color_pct(val):
    """수익률 셀 색상"""
    if val == "–" or not isinstance(val, str) or "%" not in val:
        return ""
    try:
        v = float(val.replace("%","").replace("+",""))
        if v > 10:  return "background-color:#c6efce; color:#276221"
        if v > 0:   return "background-color:#ebf5eb; color:#276221"
        if v < 0:   return "background-color:#ffc7ce; color:#9c0006"
    except:
        pass
    return ""

# ══════════════════════════════════════════════════════════════
# Streamlit UI
# ══════════════════════════════════════════════════════════════

st.set_page_config(page_title="글로벌 연기금 데이터 뷰어", layout="wide", page_icon="🌐")

st.title("🌐 글로벌 연기금 / 국부펀드 투자 데이터")
st.caption("CPP · OTPP · PSP · NZ Super · CDPQ · Future Fund · GPFG(Norway) · CalPERS  |  16개 보고서 기준")

# 사이드바 – 필터
st.sidebar.header("🔍 필터")
selected_funds = st.sidebar.multiselect(
    "펀드 선택 (전체 = 미선택)",
    options=FUNDS,
    default=[],
)
filter_funds = selected_funds if selected_funds else FUNDS

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 자산배분 상세",
    "🌏 국가별 익스포져",
    "📈 Asset Class별 수익률",
    "📅 다년도 수익률 추이",
])

# ─── TAB 1: 자산배분 ──────────────────────────────────────────
with tab1:
    st.subheader("자산배분 상세 (Allocation Detail)")
    alloc_cols = ["주식 합계","상장주식","사모주식","채권/FI","부동산","인프라","크레딧","대체투자","현금/기타"]
    data = [r for r in ALLOCATION_DETAIL if r["fund"] in filter_funds]

    for fund in filter_funds:
        rows = [r for r in data if r["fund"] == fund]
        if not rows: continue
        st.markdown(f"#### {fund}")
        display = []
        for r in rows:
            row = {"연도": r["year"], "AUM": f"{r['aum']:,} {r['currency']}"}
            for c in alloc_cols:
                v = r.get(c)
                row[c] = f"{v*100:.1f}%" if v is not None else "–"
            row["비고"] = r.get("notes","")
            display.append(row)
        df = pd.DataFrame(display).set_index("연도")
        st.dataframe(df, use_container_width=True)

# ─── TAB 2: 지역별 익스포져 ────────────────────────────────────
with tab2:
    st.subheader("국가별 익스포져 (Geographic Exposure)")
    geo_cols = ["북미 전체","미국","캐나다","뉴질랜드","유럽","아시아태평양","중남미","호주","기타/EM"]
    data = [r for r in GEOGRAPHIC_EXPOSURE if r["fund"] in filter_funds]

    for fund in filter_funds:
        rows = [r for r in data if r["fund"] == fund]
        if not rows: continue
        st.markdown(f"#### {fund}")
        display = []
        for r in rows:
            row = {"연도": r["year"]}
            for c in geo_cols:
                v = r.get(c)
                row[c] = f"{v*100:.1f}%" if v is not None else "–"
            row["비고"] = r.get("notes","")
            display.append(row)
        df = pd.DataFrame(display).set_index("연도")
        # 데이터 있는 열만 표시
        non_empty = [c for c in geo_cols if any(df[c] != "–")] + ["비고"]
        st.dataframe(df[non_empty], use_container_width=True)

# ─── TAB 3: 수익률 ─────────────────────────────────────────────
with tab3:
    st.subheader("Asset Class별 1년 수익률 (Returns by Asset Class)")
    ret_cols = ["총 펀드","상장주식","사모주식","채권/FI","부동산","인프라","크레딧","대체투자","실물자산"]
    data = [r for r in RETURNS_BY_ASSET_CLASS if r["fund"] in filter_funds]

    for fund in filter_funds:
        rows = [r for r in data if r["fund"] == fund]
        if not rows: continue
        st.markdown(f"#### {fund}")
        display = []
        for r in rows:
            row = {"연도": r["year"]}
            for c in ret_cols:
                v = r.get(c)
                row[c] = f"{v*100:+.2f}%" if v is not None else "–"
            row["비고"] = r.get("notes","")
            display.append(row)
        df = pd.DataFrame(display).set_index("연도")
        non_empty = [c for c in ret_cols if any(df[c] != "–")] + ["비고"]
        styled = df[non_empty].style.applymap(color_pct, subset=[c for c in non_empty if c != "비고"])
        st.dataframe(styled, use_container_width=True)

# ─── TAB 4: 다년도 수익률 ──────────────────────────────────────
with tab4:
    st.subheader("다년도 수익률 추이 (Multi-Year Returns)")
    myr_cols = ["1년(최신)","1년(전년)","5년(연환)","10년(연환)","설정이후"]

    data = [r for r in MULTI_YEAR_RETURNS if r["fund"] in filter_funds]
    if data:
        display = []
        for r in data:
            row = {"펀드": r["fund"], "연도": r["year"], "통화": r["currency"], "FY종료": r["FY종료"]}
            for c in myr_cols:
                v = r.get(c)
                row[c] = f"{v*100:.1f}%" if v is not None else "–"
            display.append(row)
        df = pd.DataFrame(display).set_index(["펀드","연도"])
        styled = df.style.applymap(color_pct, subset=myr_cols)
        st.dataframe(styled, use_container_width=True)

    # 차트: 1년 수익률 비교
    st.divider()
    st.markdown("##### 최신 1년 수익률 비교 차트")
    chart_data = []
    for r in MULTI_YEAR_RETURNS:
        if r["fund"] not in filter_funds: continue
        if r.get("1년(최신)") is not None:
            chart_data.append({"펀드 (연도)": f"{r['fund']} {r['year']}", "1년 수익률": r["1년(최신)"] * 100})
    if chart_data:
        cdf = pd.DataFrame(chart_data).set_index("펀드 (연도)")
        # 최신 연도만 (펀드당 1개)
        cdf = cdf[~cdf.index.duplicated(keep="first")]
        st.bar_chart(cdf, height=350)
