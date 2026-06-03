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
    """텍스트 추출 → gpt-4o-mini로 요약"""
    if not client:
        return ""

    filename = uploaded_file.name
    text = extract_text_from_pdf(uploaded_file)

    if not text.strip():
        return f"[{filename}] (텍스트 추출 실패)\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Pension fund report excerpt from '{filename}':\n\n"
                        f"{text}\n\n"
                        "In 250 words, summarize: "
                        "(1) asset allocation and changes, "
                        "(2) private market exposure (PE/Private Credit/Infrastructure/Real Estate/Secondaries), "
                        "(3) key risks and opportunities, "
                        "(4) liquidity stance. "
                        "Be concise and factual."
                    )
                }
            ]
        )
        summary = response.choices[0].message.content
    except Exception as e:
        st.warning(f"'{filename}' 요약 실패: {e}")
        summary = ""

    return f"[{filename}]\n{summary}"


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

    if uploaded_reports and client:

        st.info(
            f"{len(uploaded_reports)}개 PDF 요약 중... (파일당 약 10~20초 소요)"
        )

        summary_bar = st.progress(0)

        for i, report in enumerate(uploaded_reports):

            with st.spinner(f"요약 중: {report.name}"):
                summary = summarize_pdf(report)
                report_summaries += summary + "\n\n"

            summary_bar.progress((i + 1) / len(uploaded_reports))

        summary_bar.empty()
        st.success(f"{len(uploaded_reports)}개 PDF 요약 완료")

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
    # PENSION MONITOR
    # ==========================================

    st.header(
        "🏦 Pension Allocation Monitor"
    )

    pension = st.selectbox(
        "Select Pension Fund",
        list(
            allocation_data.keys()
        )
    )

    alloc = allocation_data[pension]

    df = pd.DataFrame(
        {
            "Asset":
            list(
                alloc.keys()
            ),
            "Weight":
            list(
                alloc.values()
            )
        }
    )

    fig = px.pie(
        df,
        names="Asset",
        values="Weight",
        title=f"{pension} Allocation"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ==========================================
    # ALLOCATION CHANGE
    # ==========================================

    st.header(
        "📈 Allocation Change Tracker"
    )

    sample_change = pd.DataFrame(
        {
            "Year":[
                "2023",
                "2023",
                "2023",
                "2024",
                "2024",
                "2024"
            ],
            "Asset":[
                "Private Equity",
                "Infrastructure",
                "Fixed Income",
                "Private Equity",
                "Infrastructure",
                "Fixed Income"
            ],
            "Weight":[
                14,
                11,
                30,
                17,
                15,
                25
            ]
        }
    )

    bar = px.bar(
        sample_change,
        x="Year",
        y="Weight",
        color="Asset",
        title="Allocation Shift"
    )

    st.plotly_chart(
        bar,
        use_container_width=True
    )

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