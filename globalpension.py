import os
import re
import io
import json
import base64
import requests
import difflib
import fitz  # pymupdf
import pandas as pd
import streamlit as st
import plotly.express as px

from openai import OpenAI

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Global Pension Intelligence Platform",
    layout="wide"
)

# =====================================================
# ENVIRONMENT
# =====================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

client = None

if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================
# KEYWORDS
# =====================================================

KEYWORDS = [
    "CalPERS",
    "CPP Investments",
    "OMERS",
    "APG",
    "AustralianSuper",
    "GPIF",
    "Private Equity",
    "Private Credit",
    "Infrastructure",
    "Secondaries"
]

# =====================================================
# UTIL
# =====================================================

def clean_html(text):
    if not text:
        return ""
    return re.sub(r"<.*?>", "", text)

# =====================================================
# NAVER NEWS
# =====================================================

@st.cache_data(ttl=3600)
def search_news(query):

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    params = {
        "query": query,
        "display": 10,
        "sort": "date"
    }

    try:

        res = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        res.raise_for_status()

        data = res.json()

        return data.get("items", [])

    except Exception as e:

        st.error(f"Naver Error: {e}")
        return []

@st.cache_data(ttl=3600)
def collect_news():

    articles = []
    seen = set()

    for keyword in KEYWORDS:

        items = search_news(keyword)

        for item in items:

            link = item.get("originallink", "")

            if link in seen:
                continue

            seen.add(link)

            articles.append(
                {
                    "keyword": keyword,
                    "title": clean_html(
                        item.get("title", "")
                    ),
                    "description": clean_html(
                        item.get("description", "")
                    ),
                    "link": link
                }
            )

    return articles

# =====================================================
# PDF 텍스트 추출 → 요약
# =====================================================

ALLOC_KEYWORDS = [
    # 배분표 직접 지칭 (고득점)
    "asset mix", "asset allocation", "asset class", "portfolio mix",
    "investment mix", "portfolio breakdown", "strategic allocation",
    "asset breakdown", "portfolio overview", "net investments",
    "% of net assets", "as at december", "as at march", "as at june",
    # 자산군 명칭
    "fixed income", "fixed-income", "private equity", "real assets",
    "inflation sensitive", "absolute return strategies",
    "public equity", "private credit", "infrastructure",
    # 점수 보조
    "total portfolio", "net assets", "equity"
]

# 배분표 고신뢰 키워드 (이게 있으면 점수 대폭 상승)
HIGH_VALUE_KEYWORDS = [
    "asset mix", "asset allocation", "net investments",
    "% of net assets", "as at december", "as at march", "as at june",
    "strategic portfolio", "portfolio breakdown", "asset class"
]

# ─── 자산군 이름 정규화 ───────────────────────────────
# 소문자·구두점 정규화 후 매핑할 canonical 이름 사전
ASSET_CANONICAL = {
    # ── Equity ──────────────────────────────────────────
    "public equity": "Public Equity",
    "public equities": "Public Equity",
    "listed equity": "Public Equity",
    "listed equities": "Public Equity",
    "global equity": "Public Equity",
    "global equities": "Public Equity",
    "private equity": "Private Equity",
    "private equities": "Private Equity",
    "pe": "Private Equity",
    "venture growth": "Venture Growth",
    "venture capital": "Venture Growth",
    # broad equity (only when no public/private split given)
    "equity": "Equity",
    "equities": "Equity",
    # ── Fixed Income ─────────────────────────────────────
    "fixed income": "Fixed Income",
    "fixed-income": "Fixed Income",
    "fixed income securities": "Fixed Income",
    "public fixed income": "Fixed Income",
    "bonds": "Fixed Income",
    "government bonds": "Fixed Income",
    "rates": "Fixed Income",
    # ── Infrastructure ───────────────────────────────────
    "unlisted infrastructure": "Infrastructure",
    "listed infrastructure": "Infrastructure",
    "real infrastructure": "Infrastructure",
    "infrastructure": "Infrastructure",
    "infra": "Infrastructure",
    # ── Real Assets (combined) ───────────────────────────
    "real assets": "Real Assets",
    # ── Real Estate ──────────────────────────────────────
    "unlisted real estate": "Real Estate",
    "listed real estate": "Real Estate",
    "real estate": "Real Estate",
    "property": "Real Estate",
    # ── Credit ───────────────────────────────────────────
    "credit investments": "Credit",
    "private credit": "Private Credit",
    "private debt": "Private Credit",
    "credit": "Credit",
    # ── Inflation Sensitive & sub-items ──────────────────
    "inflation sensitive": "Inflation Sensitive",
    "inflation-sensitive": "Inflation Sensitive",
    "inflation hedge": "Inflation Hedge",
    "inflation hedging": "Inflation Hedge",
    "real return": "Inflation Sensitive",
    "commodities": "Commodities",
    "commodity": "Commodities",
    # ── Natural Resources ────────────────────────────────
    "natural resources": "Natural Resources",
    "natural resource": "Natural Resources",
    # ── Absolute Return / Alternatives ───────────────────
    "absolute return strategies": "Absolute Return",
    "absolute return strategy": "Absolute Return",
    "absolute return": "Absolute Return",
    "alternatives": "Alternatives",
    "alternative investments": "Alternatives",
    "hedge funds": "Alternatives",
    # ── Secondaries ──────────────────────────────────────
    "secondaries": "Secondaries",
    # ── Cash ─────────────────────────────────────────────
    "cash and cash equivalents": "Cash",
    "cash and equivalents": "Cash",
    "short term investments": "Cash",
    "money market": "Cash",
    "cash": "Cash",
    # ── Renewable Energy ─────────────────────────────────
    "unlisted renewable energy infrastructure": "Renewable Energy Infrastructure",
    "renewable energy infrastructure": "Renewable Energy Infrastructure",
    "renewable energy": "Renewable Energy Infrastructure",
}

def normalize_asset_name(raw_name: str) -> str:
    """자산군 이름을 canonical 형태로 정규화."""
    key = re.sub(r"[^a-z0-9 ]", "", raw_name.lower()).strip()
    # 완전 일치 먼저
    if key in ASSET_CANONICAL:
        return ASSET_CANONICAL[key]
    # 부분 일치 — 긴 키(더 구체적)부터 매칭해야 "equities"가 "public equities"를 가로채지 않음
    sorted_keys = sorted(ASSET_CANONICAL.keys(), key=len, reverse=True)
    for k in sorted_keys:
        if k in key or key in k:
            return ASSET_CANONICAL[k]
    # 그래도 없으면 Title Case 반환
    return raw_name.strip().title()


import re as _re

def get_top_pages_text(uploaded_file, max_pages=8, max_chars=12000):
    """
    전체 PDF를 스캔 → 배분표 관련 키워드 점수가 높은 페이지의 텍스트를 반환.
    텍스트 테이블(DETAILED ASSET MIX 등)은 이미지보다 텍스트 추출이 훨씬 정확함.
    """
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        del file_bytes

        scored = []
        for i, page in enumerate(doc):
            t = page.get_text() or ""
            tl = t.lower()
            # 일반 키워드 점수
            score = sum(1 for kw in ALLOC_KEYWORDS if kw in tl)
            # 고신뢰 키워드 3배 가중치
            score += sum(3 for kw in HIGH_VALUE_KEYWORDS if kw in tl)
            # % 숫자 개수 보너스 (배분표에 많이 등장)
            pct_count = len(_re.findall(r'\d+\.?\d*\s*%', t))
            score += min(pct_count, 15)
            # 앞 3페이지 소폭 보너스 (요약 배분이 앞에 있는 경우)
            if i < 3:
                score += 3
            if score > 0:
                scored.append((score, i, t))

        # 점수 높은 순 정렬 → 상위 max_pages 선택 → 페이지 순서 복원
        scored.sort(key=lambda x: -x[0])
        top = sorted(scored[:max_pages], key=lambda x: x[1])

        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            f"[Page {idx+1}]\n{txt}" for _, idx, txt in top
        )
        doc.close()
        return combined[:max_chars]

    except Exception as e:
        st.warning(f"텍스트 추출 실패: {e}")
        return ""


def summarize_pdf(uploaded_file):
    """
    배분표 관련 페이지의 텍스트를 추출 → gpt-4o-mini로 분석.
    텍스트 테이블(DETAILED ASSET MIX 등)은 텍스트 추출이 비전보다 정확함.
    반환: (summary_text: str, fund_name: str, year: str, allocation: dict)
    """
    if not client:
        return "", "", "", {}

    filename = uploaded_file.name
    page_text = get_top_pages_text(uploaded_file, max_pages=8, max_chars=12000)

    if not page_text.strip():
        return f"[{filename}] (텍스트 추출 실패)\n", filename, "", {}

    prompt = f"""Below are selected pages from a pension fund annual report (filename: '{filename}').

Your task: find the PRIMARY asset allocation table (e.g. "Detailed Asset Mix", "Net Investments", "Portfolio Overview") showing all major asset classes and their percentage weights.

Return ONLY this JSON:
{{
  "fund_name": "<full official fund name exactly as printed>",
  "report_year": "<fiscal year end as 4-digit string, e.g. '2024'>",
  "summary": "<120-word summary: allocation changes, private markets exposure, risks, opportunities>",
  "allocation_source": "<which table/section you used, e.g. 'Detailed Asset Mix table'>",
  "allocation": {{
    "<asset class name exactly as in the table>": <% as number, positive only>
  }},
  "allocation_found": true or false
}}

STRICT RULES:
1. Use ONLY ONE table — prefer the most detailed asset mix table (e.g. "Detailed Asset Mix").
2. Use the LEAF-LEVEL (most granular) rows, not subtotal/parent rows. For example, if the table shows "Public equity 18%", "Private equity 19%", "Venture growth 6%" under an "Equity" header, extract each sub-item separately — do NOT use the "Equity 43%" subtotal.
3. EXCEPTION: If a category has no sub-items in the table (e.g. "Fixed income 23%", "Credit 14%"), keep it as-is.
4. EXCEPTION: If the table only shows "Real Assets" as a single combined line (no sub-items), keep it as one key.
5. If the table shows dollar amounts only, calculate % = each item / sum of positive items × 100.
6. EXCLUDE items with negative values (leverage, funding, borrowing, "funding and other").
7. The allocation values (after excluding negatives) must sum to approximately 100%.
8. If no clear allocation table exists in the text, return "allocation": {{}} and "allocation_found": false.
9. NEVER fabricate or estimate. Only use numbers explicitly in the text.
10. Use the exact category name as written in the table (e.g. "Public equity", "Venture growth", "Inflation hedge", "Natural resources").

PAGES:
{page_text}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}]
        )
        data = json.loads(response.choices[0].message.content)
        fund_name = data.get("fund_name", filename)
        year = str(data.get("report_year", ""))
        summary = data.get("summary", "")
        alloc_source = data.get("allocation_source", "")
        raw_alloc = data.get("allocation", {})
        found = data.get("allocation_found", bool(raw_alloc))

        # 자산군 이름 정규화 + 음수/0 제거 + 동일 canonical 합산
        allocation = {}
        for k, v in raw_alloc.items():
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            if val <= 0:
                continue
            canonical = normalize_asset_name(k)
            allocation[canonical] = allocation.get(canonical, 0) + val

        total = sum(allocation.values())

        if not found or not allocation or total < 30:
            # 데이터 없거나 너무 적음
            st.warning(f"⚠️ **'{filename}'**: 배분 데이터를 확인하지 못했습니다.")
            allocation = {}
        else:
            # 정규화 하지 않음 — 원본 PDF 비중 그대로 유지
            # (레버리지 구조 펀드는 양수 합계가 100% 초과할 수 있음)
            note = f" (합계 {total:.1f}%)" if not (90 <= total <= 110) else ""
            with st.expander(f"📋 '{filename}' 추출 내역{note}"):
                st.caption(f"출처: {alloc_source or '-'}")
                st.json({k: f"{v:.1f}%" for k, v in allocation.items()})

    except Exception as e:
        st.warning(f"'{filename}' 분석 실패: {e}")
        return f"[{filename}] 분석 실패\n", filename, "", {}

    label = f"{fund_name} ({year})" if year else fund_name
    return f"[{label}]\n{summary}", fund_name, year, allocation


# =====================================================
# OPENAI 최종 분석
# =====================================================

def analyze_intelligence(articles, report_summaries=""):

    if not client:
        return None

    news_text = "\n".join(
        [
            f"- {x['title']} | {x['description']}"
            for x in articles[:50]
        ]
    )

    prompt = f"""You are CIO advisor for a Korean insurance company.

Based on the pension report summaries and news below, analyze:
1. Global pension allocation shifts
2. Private market trends (PE, Private Credit, Infrastructure, Real Estate, Secondaries)
3. Key opportunities for Korean insurers
4. Risk alerts
5. Liquidity concerns

Return ONLY this JSON structure:
{{
 "signals": {{
   "Private Equity": "",
   "Private Credit": "",
   "Infrastructure": "",
   "Real Estate": "",
   "Secondaries": ""
 }},
 "brief": "",
 "opportunities": [],
 "risk_alerts": [],
 "implications": ""
}}

PENSION REPORT SUMMARIES:
{report_summaries if report_summaries else "(No reports uploaded)"}

NEWS:
{news_text}
"""

    try:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}]
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:

        st.error(f"OpenAI Error: {e}")
        return None

# =====================================================
# SAMPLE ALLOCATION DATA
# =====================================================

allocation_data = {

    "CalPERS": {
        "Public Equity": 42,
        "Private Equity": 17,
        "Fixed Income": 25,
        "Real Assets": 10,
        "Cash": 6
    },

    "CPP Investments": {
        "Public Equity": 25,
        "Private Equity": 31,
        "Fixed Income": 15,
        "Infrastructure": 19,
        "Cash": 10
    },

    "APG": {
        "Public Equity": 35,
        "Private Equity": 12,
        "Fixed Income": 32,
        "Infrastructure": 15,
        "Cash": 6
    },

    "AustralianSuper": {
        "Public Equity": 39,
        "Private Equity": 16,
        "Fixed Income": 18,
        "Infrastructure": 21,
        "Cash": 6
    },

    "GPIF": {
        "Domestic Equity": 25,
        "Foreign Equity": 25,
        "Domestic Bond": 25,
        "Foreign Bond": 25
    }
}

# =====================================================
# HEADER
# =====================================================

st.title(
    "🌍 Global Pension Intelligence Platform"
)

st.caption(
    "News + Pension Reports + AI Investment Intelligence"
)

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.header("Settings")

uploaded_reports = st.sidebar.file_uploader(
    "Upload Pension Reports (PDF, 개수 제한 없음)",
    type=["pdf"],
    accept_multiple_files=True
)

run_button = st.sidebar.button(
    "🚀 Run Analysis",
    use_container_width=True
)

# =====================================================
# MAIN
# =====================================================

def normalize_fund_name(new_name, existing_names, threshold=0.82):
    """
    새 펀드명을 기존 이름 목록과 비교해 유사한 이름이 있으면 그것을 반환.
    없으면 new_name 그대로 반환.
    """
    if not existing_names:
        return new_name
    # 대소문자·구두점 무시한 정규화
    def clean(s):
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    clean_new = clean(new_name)
    best_match = None
    best_score = 0.0

    for name in existing_names:
        score = difflib.SequenceMatcher(None, clean_new, clean(name)).ratio()
        if score > best_score:
            best_score = score
            best_match = name

    return best_match if best_score >= threshold else new_name


if run_button:

    report_summaries = ""
    # {fund_name: {year: {asset: weight}}}
    fund_timeseries = {}

    if uploaded_reports and client:

        st.info(
            f"{len(uploaded_reports)}개 PDF 요약 중... (파일당 약 10~20초 소요)"
        )

        summary_bar = st.progress(0)

        for i, report in enumerate(uploaded_reports):

            with st.spinner(f"요약 중: {report.name}"):
                summary, fund_name, year, allocation = summarize_pdf(report)
                report_summaries += summary + "\n\n"
                if allocation and fund_name:
                    # 유사한 펀드명이 이미 있으면 그 이름으로 통합
                    canonical = normalize_fund_name(fund_name, list(fund_timeseries.keys()))
                    if canonical not in fund_timeseries:
                        fund_timeseries[canonical] = {}
                    fund_timeseries[canonical][year or "Unknown"] = allocation

            summary_bar.progress((i + 1) / len(uploaded_reports))

        summary_bar.empty()
        st.success(f"{len(uploaded_reports)}개 PDF 요약 완료")
        st.session_state["fund_timeseries"] = fund_timeseries

    with st.spinner(
        "Collecting news..."
    ):

        articles = collect_news()

    st.success(
        f"{len(articles)} articles collected"
    )

    result = None

    if client:

        with st.spinner("AI analyzing..."):
            result = analyze_intelligence(articles, report_summaries)

    # session_state에 저장 (드롭다운 선택 시 유지)
    st.session_state["result"] = result
    st.session_state["articles"] = articles

else:
    # run_button이 눌리지 않았을 때 session_state에서 복원
    result = st.session_state.get("result", None)
    articles = st.session_state.get("articles", [])
    fund_timeseries = st.session_state.get("fund_timeseries", {})


# =====================================================
# 결과 렌더링 (session_state 기반 → 드롭다운 선택해도 유지)
# =====================================================

if result or fund_timeseries or articles:

    # ==========================================
    # EXECUTIVE RADAR
    # ==========================================

    st.header("📊 Executive Radar")

    cols = st.columns(5)
    assets = ["Private Equity", "Private Credit", "Infrastructure", "Real Estate", "Secondaries"]

    for i, asset in enumerate(assets):
        value = result.get("signals", {}).get(asset, "-") if result else "-"
        cols[i].metric(asset, value)

    # ==========================================
    # AI BRIEF
    # ==========================================

    st.header("🧠 AI Brief")
    if result:
        st.info(result.get("brief", ""))

    # ==========================================
    # OPPORTUNITIES
    # ==========================================

    st.header("🎯 Opportunity Watchlist")
    if result:
        for item in result.get("opportunities", []):
            st.success(item)

    # ==========================================
    # RISK ALERT
    # ==========================================

    st.header("🚨 Risk Alerts")
    if result:
        alerts = result.get("risk_alerts", [])
        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("No Risk Alerts")

    # ==========================================
    # INSURER IMPLICATIONS
    # ==========================================

    st.header("🏢 Korean Insurer Implications")
    if result:
        st.write(result.get("implications", ""))

    # ==========================================
    # PENSION MONITOR
    # ==========================================

    st.header("🏦 Pension Allocation Monitor")

    if fund_timeseries:
        fund_names = list(fund_timeseries.keys())
        selected_fund = st.selectbox("Select Pension Fund", fund_names, key="sel_fund")
        years_available = sorted(fund_timeseries[selected_fund].keys(), reverse=True)
        selected_year = st.selectbox("Select Year", years_available, key="sel_year")

        alloc = fund_timeseries[selected_fund][selected_year]
        df_bar = pd.DataFrame({
            "Asset": list(alloc.keys()),
            "Weight": [round(float(v), 1) for v in alloc.values()]
        }).sort_values("Weight", ascending=True)

        total = df_bar["Weight"].sum()
        note = f" (합계 {total:.1f}% — 레버리지 구조)" if not (90 <= total <= 110) else ""

        fig = px.bar(
            df_bar, x="Weight", y="Asset", orientation="h",
            title=f"{selected_fund} ({selected_year}) Allocation{note}",
            text="Weight",
            labels={"Weight": "Asset Mix (%)", "Asset": ""}
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(xaxis_title="Asset Mix (%)", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("PDF를 업로드하고 Run Analysis를 실행하면 실제 배분 데이터가 표시됩니다.")

    # ==========================================
    # ALLOCATION CHANGE TRACKER
    # ==========================================

    st.header("📈 Allocation Change Tracker")

    if fund_timeseries:
        multi_year_funds = {f: d for f, d in fund_timeseries.items() if len(d) >= 2}

        if multi_year_funds:
            tracker_fund = st.selectbox(
                "펀드 선택 (시계열)", list(multi_year_funds.keys()), key="tracker_fund"
            )
            rows = []
            for year, alloc_dict in sorted(multi_year_funds[tracker_fund].items()):
                total = sum(float(v) for v in alloc_dict.values())
                for asset, weight in alloc_dict.items():
                    rows.append({
                        "Year": str(year),
                        "Asset": asset,
                        "Weight": round(float(weight) / total * 100, 1) if total else float(weight)
                    })
            df_bar = pd.DataFrame(rows)
            bar = px.bar(
                df_bar, x="Year", y="Weight", color="Asset",
                title=f"{tracker_fund} — Allocation Change Over Time (%)",
                barmode="stack", range_y=[0, 100]
            )
            bar.update_layout(yaxis_title="Weight (%)")
            st.plotly_chart(bar, use_container_width=True)

        else:
            st.caption("같은 펀드의 여러 연도 보고서를 업로드하면 시계열 차트가 표시됩니다. 현재는 펀드 간 비교 차트를 표시합니다.")
            rows = []
            for fund_name, ydata in fund_timeseries.items():
                for year, alloc_dict in ydata.items():
                    total = sum(float(v) for v in alloc_dict.values())
                    for asset, weight in alloc_dict.items():
                        rows.append({
                            "Fund": f"{fund_name} ({year})",
                            "Asset": asset,
                            "Weight": round(float(weight) / total * 100, 1) if total else float(weight)
                        })
            df_bar = pd.DataFrame(rows)
            bar = px.bar(
                df_bar, x="Fund", y="Weight", color="Asset",
                title="Uploaded Funds — Asset Allocation Comparison (%)",
                barmode="stack", range_y=[0, 100]
            )
            bar.update_layout(xaxis_tickangle=-20, yaxis_title="Weight (%)")
            st.plotly_chart(bar, use_container_width=True)

    else:
        st.info("같은 펀드의 여러 연도 보고서를 업로드하면 시계열 변화를 추적합니다.")

    # ==========================================
    # NEWS
    # ==========================================

    st.header("📰 Latest News")

    for row in articles[:30]:
        with st.expander(row["title"]):
            st.write(row["description"])
            if row["link"]:
                st.markdown(f"[Original Article]({row['link']})")

else:
    st.info("Click 'Run Analysis' to start.")