import os
import re
import io
import json
import base64
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

ALLOC_KEYWORDS = [
    "asset mix", "asset allocation", "asset class", "portfolio mix",
    "allocation", "equity", "fixed income", "infrastructure",
    "private equity", "real assets", "credit", "% of net assets",
    "net investments", "portfolio breakdown", "investment mix",
    "total portfolio", "net assets"
]

def get_top_pages_as_images(uploaded_file, max_pages=5, dpi=120):
    """
    키워드 점수가 높은 페이지를 이미지로 렌더링해 base64 목록 반환.
    텍스트가 없는 차트/이미지 페이지도 정확하게 인식.
    """
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf")
        del file_bytes

        scored = []
        for i, page in enumerate(doc):
            t = page.get_text() or ""
            score = sum(1 for kw in ALLOC_KEYWORDS if kw.lower() in t.lower())
            # 텍스트가 거의 없어도(이미지 페이지) 앞 5페이지는 포함
            if score > 0 or i < 5:
                scored.append((score, i))

        # 상위 페이지 선택
        top_idxs = sorted(
            sorted(scored, key=lambda x: -x[0])[:max_pages],
            key=lambda x: x[1]  # 페이지 순서 복원
        )

        images_b64 = []
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for _, idx in top_idxs:
            pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
            png_bytes = pix.tobytes("png")
            images_b64.append(base64.b64encode(png_bytes).decode())
            pix = None  # 메모리 해제

        doc.close()
        return images_b64

    except Exception as e:
        st.warning(f"페이지 이미지 변환 실패: {e}")
        return []


def summarize_pdf(uploaded_file):
    """
    PDF 핵심 페이지를 이미지로 렌더링 → GPT-4o 비전으로 정확 추출.
    반환: (summary_text: str, fund_name: str, year: str, allocation: dict)
    """
    if not client:
        return "", "", "", {}

    filename = uploaded_file.name
    images_b64 = get_top_pages_as_images(uploaded_file, max_pages=5, dpi=120)

    if not images_b64:
        return f"[{filename}] (이미지 변환 실패)\n", filename, "", {}

    content = []
    for b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64}",
                "detail": "high"
            }
        })

    content.append({
        "type": "text",
        "text": f"""These are pages from pension fund annual report '{filename}'.

Return ONLY this JSON:
{{
  "fund_name": "<official fund name>",
  "report_year": "<fiscal year end year, e.g. 2024>",
  "summary": "<150-word summary: allocation, private markets, risks, opportunities>",
  "allocation": {{
    "<asset class name exactly as shown>": <% as number>
  }},
  "allocation_found": true or false
}}

STRICT RULES:
1. Copy asset class names EXACTLY as shown in charts/tables.
2. Use ONLY percentages explicitly shown — read directly from the page.
3. If amounts are in dollars, calculate % using the total shown.
4. Exclude leverage/funding items (negative values).
5. If no allocation data is visible, return "allocation": {{}} and "allocation_found": false.
6. NEVER guess or fabricate numbers."""
    })

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": content}]
        )
        data = json.loads(response.choices[0].message.content)
        fund_name = data.get("fund_name", filename)
        year = str(data.get("report_year", ""))
        summary = data.get("summary", "")
        allocation = data.get("allocation", {})
        found = data.get("allocation_found", bool(allocation))

        if not found or not allocation:
            st.warning(f"'{filename}': 배분 데이터를 시각적으로 확인하지 못했습니다.")
            allocation = {}

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
        total = sum(float(v) for v in alloc.values())
        df_pie = pd.DataFrame({
            "Asset": list(alloc.keys()),
            "Weight": [round(float(v) / total * 100, 1) if total else float(v) for v in alloc.values()]
        })
        fig = px.pie(
            df_pie, names="Asset", values="Weight",
            title=f"{selected_fund} ({selected_year}) Allocation"
        )
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