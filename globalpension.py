import os
import json
import requests
import streamlit as st
from openai import OpenAI

# =====================================================

# PAGE CONFIG

# =====================================================

st.set_page_config(
page_title="Global Pension Radar",
layout="wide"
)

# =====================================================

# ENVIRONMENT VARIABLES

# =====================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

# =====================================================

# OPENAI CLIENT

# =====================================================

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
"APG Pension",
"AustralianSuper",
"GPIF",
"Private Credit",
"Infrastructure",
"Private Equity",
"Secondaries"
]

# =====================================================

# NAVER NEWS API

# =====================================================

@st.cache_data(ttl=3600)
def search_news(query):

```
if not NAVER_CLIENT_ID:
    return []

if not NAVER_CLIENT_SECRET:
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

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    return data.get("items", [])

except Exception as e:

    st.error(f"Naver API Error: {e}")

    return []
```

@st.cache_data(ttl=3600)
def collect_news():

```
articles = []

for keyword in KEYWORDS:

    news_items = search_news(keyword)

    for item in news_items:

        articles.append(
            {
                "keyword": keyword,
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "link": item.get("originallink", "")
            }
        )

return articles
```

# =====================================================

# OPENAI ANALYSIS

# =====================================================

def analyze_articles(articles):

```
if not client:
    return None

if not articles:
    return None

sample = articles[:50]

news_text = "\n".join(
    [
        f"- {x['title']} | {x['description']}"
        for x in sample
    ]
)

prompt = f"""
```

You are a global pension investment strategist.

Analyze the following news.

Return ONLY JSON.

{{
"signals": {{
"Private Equity": "",
"Private Credit": "",
"Infrastructure": "",
"Real Estate": "",
"Secondaries": ""
}},
"brief": "",
"risk_alerts": []
}}

News:

{news_text}
"""

```
try:

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    content = response.choices[0].message.content

    start = content.find("{")
    end = content.rfind("}")

    if start >= 0 and end >= 0:
        content = content[start:end + 1]

    return json.loads(content)

except Exception as e:

    st.error(f"OpenAI Error: {e}")

    return None
```

# =====================================================

# HEADER

# =====================================================

st.title("🌍 Global Pension Radar")

st.caption(
"AI 기반 해외 연기금 대체투자 시그널 분석"
)

# =====================================================

# SIDEBAR

# =====================================================

st.sidebar.header("Settings")

run_button = st.sidebar.button(
"🚀 분석 실행",
use_container_width=True
)

# =====================================================

# MAIN

# =====================================================

if run_button:

```
with st.spinner("뉴스 수집 중..."):

    articles = collect_news()

st.success(
    f"{len(articles)}건 기사 수집 완료"
)

result = None

if client:

    with st.spinner("AI 분석 중..."):

        result = analyze_articles(articles)

# =================================================
# EXECUTIVE RADAR
# =================================================

st.header("📊 Executive Radar")

default_signals = {
    "Private Equity": "-",
    "Private Credit": "-",
    "Infrastructure": "-",
    "Real Estate": "-",
    "Secondaries": "-"
}

if result:
    signals = result.get(
        "signals",
        default_signals
    )
else:
    signals = default_signals

cols = st.columns(5)

assets = [
    "Private Equity",
    "Private Credit",
    "Infrastructure",
    "Real Estate",
    "Secondaries"
]

for i, asset in enumerate(assets):

    cols[i].metric(
        asset,
        signals.get(asset, "-")
    )

# =================================================
# AI BRIEF
# =================================================

st.header("🧠 AI Brief")

if result:

    st.info(
        result.get(
            "brief",
            "분석 결과 없음"
        )
    )

else:

    st.info(
        "OpenAI 분석 결과 없음"
    )

# =================================================
# RISK ALERT
# =================================================

st.header("🚨 Risk Alerts")

if result:

    alerts = result.get(
        "risk_alerts",
        []
    )

    if alerts:

        for alert in alerts:
            st.warning(alert)

    else:
        st.success("Risk Alert 없음")

# =================================================
# PENSION MAP
# =================================================

st.header("🏦 Pension Allocation Map")

st.table([
    {
        "Institution": "CalPERS",
        "PE": "High",
        "Credit": "Medium",
        "Infra": "High",
        "RE": "Low"
    },
    {
        "Institution": "CPP",
        "PE": "High",
        "Credit": "High",
        "Infra": "High",
        "RE": "Low"
    },
    {
        "Institution": "APG",
        "PE": "Medium",
        "Credit": "Medium",
        "Infra": "High",
        "RE": "Medium"
    },
    {
        "Institution": "AustralianSuper",
        "PE": "High",
        "Credit": "Medium",
        "Infra": "High",
        "RE": "Medium"
    },
    {
        "Institution": "GPIF",
        "PE": "Medium",
        "Credit": "Low",
        "Infra": "Medium",
        "RE": "Low"
    }
])

# =================================================
# NEWS
# =================================================

st.header("📰 Latest News")

if not articles:

    st.warning("수집된 뉴스 없음")

else:

    for row in articles[:30]:

        with st.expander(row["title"]):

            st.write(row["description"])

            if row["link"]:

                st.markdown(
                    f"[원문 보기]({row['link']})"
                )
```
