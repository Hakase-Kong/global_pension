import os
import re
import io
import json
import requests
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

EXTRACT_PAGES = 8       # 파일당 최대 페이지 수
EXTRACT_CHARS = 6000    # 페이지당 추출 문자 수 합산 한도

def extract_text_from_pdf(uploaded_file):
    """pymupdf로 앞부분 텍스트만 빠르게 추출 후 메모리 해제"""
    text = ""
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        del file_bytes  # 원본 bytes 즉시 해제

        for i, page in enumerate(doc):
            if i >= EXTRACT_PAGES or len(text) >= EXTRACT_CHARS:
                break
            t = page.get_text()
            if t:
                text += t + "\n"

        doc.close()
    except Exception as e:
        st.warning(f"텍스트 추출 실패: {e}")

    return text[:EXTRACT_CHARS]


def summarize_pdf(uploaded_file):
    """
    텍스트 추출 → gpt-4o-mini로 요약 + 자산배분 JSON 추출.
    반환: (summary_text: str, fund_name: str, allocation: dict)
    """
    if not client:
        return "", "", "", {}

    filename = uploaded_file.name
    text = extract_text_from_pdf(uploaded_file)

    if not text.strip():
        return f"[{filename}] (텍스트 추출 실패)\n", filename, "", {}

    prompt = f"""Pension fund report excerpt from '{filename}':

{text}

Return ONLY a JSON object with this exact structure:
{{
  "fund_name": "<official fund name, e.g. NZ Super Fund>",
  "report_year": "<year, e.g. 2024>",
  "summary": "<250-word summary covering: asset allocation changes, private market exposure (PE/Private Credit/Infrastructure/Real Estate/Secondaries), key risks and opportunities, liquidity stance>",
  "allocation": {{
    "<asset class>": <percentage as number>,
    ...
  }}
}}

For allocation, extract the actual percentage weights from the report.
Use asset class names like: Public Equity, Private Equity, Fixed Income, Infrastructure, Real Estate, Private Credit, Cash, Alternatives, Secondaries.
Only include asset classes explicitly mentioned with weights in the report."""

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
        allocation = data.get("allocation", {})

    except Exception as e:
        st.warning(f"'{filename}' 요약 실패: {e}")
        return f"[{filename}] 요약 실패\n", filename, "", {}

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
                    if fund_name not in fund_timeseries:
                        fund_timeseries[fund_name] = {}
                    fund_timeseries[fund_name][year or "Unknown"] = allocation

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

        with st.spinner(
            "AI analyzing..."
        ):

            result = analyze_intelligence(
                articles,
                report_summaries
            )

    # ==========================================
    # EXECUTIVE RADAR
    # ==========================================

    st.header(
        "📊 Executive Radar"
    )

    cols = st.columns(5)

    assets = [
        "Private Equity",
        "Private Credit",
        "Infrastructure",
        "Real Estate",
        "Secondaries"
    ]

    for i, asset in enumerate(assets):

        value = "-"

        if result:
            value = (
                result
                .get("signals", {})
                .get(asset, "-")
            )

        cols[i].metric(
            asset,
            value
        )

    # ==========================================
    # AI BRIEF
    # ==========================================

    st.header(
        "🧠 AI Brief"
    )

    if result:

        st.info(
            result.get(
                "brief",
                ""
            )
        )

    # ==========================================
    # OPPORTUNITIES
    # ==========================================

    st.header(
        "🎯 Opportunity Watchlist"
    )

    if result:

        for item in result.get(
            "opportunities",
            []
        ):
            st.success(item)

    # ==========================================
    # RISK ALERT
    # ==========================================

    st.header(
        "🚨 Risk Alerts"
    )

    if result:

        alerts = result.get(
            "risk_alerts",
            []
        )

        if alerts:

            for alert in alerts:
                st.warning(alert)

        else:
            st.success(
                "No Risk Alerts"
            )

    # ==========================================
    # INSURER IMPLICATIONS
    # ==========================================

    st.header(
        "🏢 Korean Insurer Implications"
    )

    if result:

        st.write(
            result.get(
                "implications",
                ""
            )
        )

    # ==========================================
    # PENSION MONITOR (업로드 PDF 횡단면)
    # ==========================================

    st.header("🏦 Pension Allocation Monitor")

    if fund_timeseries:
        # 업로드된 각 펀드의 최신 연도 배분을 파이차트로 표시
        fund_names = list(fund_timeseries.keys())
        selected_fund = st.selectbox("Select Pension Fund", fund_names)

        years_available = sorted(fund_timeseries[selected_fund].keys(), reverse=True)
        selected_year = st.selectbox("Select Year", years_available)

        alloc = fund_timeseries[selected_fund][selected_year]
        df_pie = pd.DataFrame({
            "Asset": list(alloc.keys()),
            "Weight": [float(v) for v in alloc.values()]
        })

        fig = px.pie(
            df_pie,
            names="Asset",
            values="Weight",
            title=f"{selected_fund} ({selected_year}) Allocation"
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("PDF를 업로드하고 Run Analysis를 실행하면 실제 배분 데이터가 표시됩니다.")

    # ==========================================
    # ALLOCATION CHANGE TRACKER (시계열)
    # ==========================================

    st.header("📈 Allocation Change Tracker")

    if fund_timeseries:
        # 여러 연도 데이터가 있는 펀드만 필터
        multi_year_funds = {
            f: ydata for f, ydata in fund_timeseries.items()
            if len(ydata) >= 2
        }

        if multi_year_funds:
            tracker_fund = st.selectbox(
                "펀드 선택 (시계열)",
                list(multi_year_funds.keys()),
                key="tracker_fund"
            )
            rows = []
            for year, alloc_dict in sorted(multi_year_funds[tracker_fund].items()):
                for asset, weight in alloc_dict.items():
                    rows.append({"Year": year, "Asset": asset, "Weight": float(weight)})

            df_bar = pd.DataFrame(rows)
            bar = px.bar(
                df_bar,
                x="Year",
                y="Weight",
                color="Asset",
                title=f"{tracker_fund} — Allocation Change Over Time",
                barmode="stack"
            )
            st.plotly_chart(bar, use_container_width=True)

        else:
            # 단일 연도만 있는 경우 → 펀드 간 횡단면 비교
            st.caption("같은 펀드의 여러 연도 보고서를 업로드하면 시계열 차트가 표시됩니다. 현재는 펀드 간 비교 차트를 표시합니다.")
            rows = []
            for fund_name, ydata in fund_timeseries.items():
                for year, alloc_dict in ydata.items():
                    for asset, weight in alloc_dict.items():
                        rows.append({
                            "Fund": f"{fund_name} ({year})",
                            "Asset": asset,
                            "Weight": float(weight)
                        })
            df_bar = pd.DataFrame(rows)
            bar = px.bar(
                df_bar,
                x="Fund",
                y="Weight",
                color="Asset",
                title="Uploaded Funds — Asset Allocation Comparison",
                barmode="stack"
            )
            bar.update_layout(xaxis_tickangle=-20)
            st.plotly_chart(bar, use_container_width=True)

    else:
        st.info("같은 펀드의 여러 연도 보고서를 업로드하면 시계열 변화를 추적합니다.")

    # ==========================================
    # NEWS
    # ==========================================

    st.header(
        "📰 Latest News"
    )

    for row in articles[:30]:

        with st.expander(
            row["title"]
        ):

            st.write(
                row["description"]
            )

            if row["link"]:

                st.markdown(
                    f"[Original Article]({row['link']})"
                )

else:

    st.info(
        "Click 'Run Analysis' to start."
    )