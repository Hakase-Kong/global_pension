import os
import json
import requests
import pandas as pd
import streamlit as st
from openai import OpenAI

# =====================================================
# CONFIG
# =====================================================

st.set_page_config(
    page_title="Global Pension Radar",
    layout="wide"
)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

KEYWORDS = [
    "CalPERS",
    "CPP Investments",
    "OMERS",
    "APG Pension",
    "AustralianSuper",
    "GPIF",
    "Pension Fund",
    "Private Credit",
    "Infrastructure",
    "Private Equity",
    "Co-investment",
    "Secondaries",
]

# =====================================================
# NAVER NEWS
# =====================================================

@st.cache_data(ttl=3600)
def search_news(query):

    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }

    params = {
        "query": query,
        "display": 20,
        "sort": "date"
    }

    try:

        res = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        data = res.json()

        return data.get("items", [])

    except Exception:
        return []


@st.cache_data(ttl=3600)
def collect_news():

    articles = []

    for keyword in KEYWORDS:

        items = search_news(keyword)

        for item in items:

            articles.append({
                "keyword": keyword,
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "link": item.get("originallink", "")
            })

    return pd.DataFrame(articles)

# =====================================================
# GPT ANALYSIS
# =====================================================

def analyze_articles(df):

    if df.empty:
        return None

    sample = df.head(80)

    article_text = "\n".join([
        f"- {row['title']} | {row['description']}"
        for _, row in sample.iterrows()
    ])

    prompt = f"""
You are an institutional private markets strategist.

Analyze the following pension fund news.

Return ONLY JSON.

{{
  "signals": {{
    "Private Equity":"",
    "Private Credit":"",
    "Infrastructure":"",
    "Real Estate":"",
    "Secondaries":""
  }},
  "brief":"",
  "risk_alerts":[],
  "asset_issues":[
    {{
      "asset":"",
      "risk_level":"",
      "issues":[]
    }}
  ],
  "rebalancing":[
    {{
      "institution":"",
      "signal":"",
      "reason":""
    }}
  ]
}}

Signal options:

Increase
Selective
Watch
Reduce
De-risking
Income Shift

News:

{article_text}
"""

    try:

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": prompt
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
# UI
# =====================================================

st.title("🌍 Global Pension Radar")

st.caption(
    "AI 기반 해외 연기금 대체투자 리밸런싱 시그널 분석"
)

# =====================================================
# SIDEBAR
# =====================================================

st.sidebar.title("Settings")

period = st.sidebar.selectbox(
    "기간",
    ["최근 7일", "최근 30일"]
)

run = st.sidebar.button(
    "🚀 분석 실행",
    use_container_width=True
)

# =====================================================
# RUN
# =====================================================

if run:

    with st.spinner("뉴스 수집 중..."):

        news_df = collect_news()

    st.success(
        f"{len(news_df)}개 기사 수집 완료"
    )

    with st.spinner("AI 분석 중..."):

        result = analyze_articles(news_df)

    if result:

        # ==========================================
        # EXECUTIVE RADAR
        # ==========================================

        st.header("📊 Executive Radar")

        signals = result.get("signals", {})

        cols = st.columns(5)

        assets = [
            "Private Equity",
            "Private Credit",
            "Infrastructure",
            "Real Estate",
            "Secondaries"
        ]

        for idx, asset in enumerate(assets):

            cols[idx].metric(
                asset,
                signals.get(asset, "-")
            )

        # ==========================================
        # AI BRIEF
        # ==========================================

        st.header("🧠 AI Brief")

        st.info(
            result.get("brief", "")
        )

        # ==========================================
        # RISK ALERT
        # ==========================================

        st.header("🚨 Risk Alerts")

        alerts = result.get(
            "risk_alerts",
            []
        )

        for alert in alerts:

            st.warning(alert)

        # ==========================================
        # PORTFOLIO MAP
        # ==========================================

        st.header(
            "🏦 Pension Allocation Map"
        )

        portfolio = pd.DataFrame(
            [
                ["CalPERS", "High", "Medium", "High", "Low", "Medium"],
                ["CPP", "High", "High", "High", "Low", "Medium"],
                ["APG", "Medium", "Medium", "High", "Medium", "Low"],
                ["AustralianSuper", "High", "Medium", "High", "Medium", "Low"],
                ["GPIF", "Medium", "Low", "Medium", "Low", "Low"]
            ],
            columns=[
                "Institution",
                "PE",
                "Credit",
                "Infra",
                "RE",
                "Secondaries"
            ]
        )

        st.dataframe(
            portfolio,
            use_container_width=True
        )

        # ==========================================
        # ASSET ISSUE RADAR
        # ==========================================

        st.header("📡 Asset Issue Radar")

        issues = result.get(
            "asset_issues",
            []
        )

        for issue in issues:

            with st.expander(
                issue.get("asset", "Asset")
            ):

                st.write(
                    f"Risk Level: {issue.get('risk_level')}"
                )

                for item in issue.get(
                    "issues",
                    []
                ):
                    st.write(
                        f"- {item}"
                    )

        # ==========================================
        # REBALANCING
        # ==========================================

        st.header(
            "🔄 Rebalancing Tracker"
        )

        rebalancing = result.get(
            "rebalancing",
            []
        )

        for row in rebalancing:

            with st.container():

                st.subheader(
                    row.get(
                        "institution",
                        ""
                    )
                )

                st.write(
                    f"Signal: {row.get('signal')}"
                )

                st.caption(
                    row.get(
                        "reason",
                        ""
                    )
                )

                st.divider()

        # ==========================================
        # NEWS
        # ==========================================

        st.header(
            "📰 Latest Pension News"
        )

        with st.expander(
            "기사 보기"
        ):

            for _, row in news_df.head(50).iterrows():

                st.markdown(
                    f"**{row['title']}**"
                )

                st.write(
                    row["description"]
                )

                if row["link"]:
                    st.markdown(
                        f"[원문 보기]({row['link']})"
                    )

                st.divider()