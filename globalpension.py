import os
import re
import base64
import json
import requests
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
# PDF
# =====================================================

def encode_pdf(uploaded_file):
    """PDF를 base64로 인코딩해서 반환 (파싱 없이 OpenAI에 직접 전달)"""
    file_bytes = uploaded_file.read()
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    del file_bytes
    return b64, uploaded_file.name

# =====================================================
# OPENAI ANALYSIS
# =====================================================

def analyze_intelligence(
    articles,
    pdf_files=None
):

    if not client:
        return None

    news_text = "\n".join(
        [
            f"- {x['title']} | {x['description']}"
            for x in articles[:50]
        ]
    )

    prompt = """You are CIO advisor for a Korean insurance company.

Analyze the attached pension reports and news below:

1. Global pension allocation shifts
2. Private market trends
3. Private credit opportunities
4. Infrastructure demand
5. Secondaries activity
6. Liquidity concerns

Return ONLY JSON.

{
 "signals": {
   "Private Equity":"",
   "Private Credit":"",
   "Infrastructure":"",
   "Real Estate":"",
   "Secondaries":""
 },
 "brief":"",
 "opportunities":[],
 "risk_alerts":[],
 "implications":""
}

NEWS:
""" + news_text

    # 메시지 content 구성: PDF 파일 + 텍스트 프롬프트
    content = []

    if pdf_files:
        for b64_data, filename in pdf_files:
            content.append({
                "type": "file",
                "file": {
                    "filename": filename,
                    "file_data": f"data:application/pdf;base64,{b64_data}"
                }
            })

    content.append({
        "type": "text",
        "text": prompt
    })

    try:

        response = client.chat.completions.create(
            model="gpt-4o",  # PDF 직접 처리는 gpt-4o 필요
            response_format={
                "type": "json_object"
            },
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        return json.loads(
            response.choices[0].message.content
        )

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
    "Upload Pension Reports (최대 3개, 각 10MB 이하 권장)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_reports and len(uploaded_reports) > 3:
    st.sidebar.warning("PDF는 최대 3개까지만 처리됩니다.")
    uploaded_reports = uploaded_reports[:3]

run_button = st.sidebar.button(
    "🚀 Run Analysis",
    use_container_width=True
)

# =====================================================
# MAIN
# =====================================================

if run_button:

    pdf_files = []

    if uploaded_reports:

        with st.spinner(
            "Encoding reports..."
        ):

            for report in uploaded_reports:
                b64, name = encode_pdf(report)
                pdf_files.append((b64, name))

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
                pdf_files if pdf_files else None
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