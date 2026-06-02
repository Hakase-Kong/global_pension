import os
import json
import requests
import streamlit as st
from openai import OpenAI

# =====================================================

# CONFIG

# =====================================================

st.set_page_config(
page_title="Global Pension Radar",
layout="wide"
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

if not OPENAI_API_KEY:
st.error("OPENAI_API_KEY not found")
st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

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
"Co-investment",
"Secondaries"
]

# =====================================================

# NAVER NEWS

# =====================================================

@st.cache_data(ttl=3600)
def search_news(query):

```
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
        timeout=15
    )

    response.raise_for_status()

    return response.json().get("items", [])

except Exception:
    return []
```

@st.cache_data(ttl=3600)
def collect_news():

```
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

return articles
```

# =====================================================

# GPT ANALYSIS

# =====================================================

def analyze_articles(articles):

```
if not articles:
    return None

sample = articles[:60]

article_text = "\n".join(
    [
        f"- {x['title']} | {x['description']}"
        for x in sample
    ]
)

prompt = f"""
```

You are a global pension fund strategist.

Analyze the following news.

Return ONLY valid JSON.

{{
"signals": {{
"Private Equity": "",
"Private Credit": "",
"Infrastructure": "",
"Real Estate": "",
"Secondaries": ""
}},
"brief": "",
"risk_alerts": [],
"asset_issues": [
{{
"asset": "",
"risk_level": "",
"issues": []
}}
],
"rebalancing": [
{{
"institution": "",
"signal": "",
"reason": ""
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

```
try:

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_object"
        }
    )

    return json.loads(
        response.choices[0].message.content
    )

except Exception as e:

    st.error(f"OpenAI Error: {e}")
    return None
```

# =====================================================

# UI HEADER

# =====================================================

st.title("🌍 Global Pension Radar")

st.caption(
"AI 기반 해외 연기금 대체투자 리밸런싱 시그널 분석"
)

# =====================================================

# SIDEBAR

# =====================================================

st.sidebar.title("Settings")

st.sidebar.markdown(
"Global Pension Intelligence Dashboard"
)

run = st.sidebar.button(
"🚀 분석 실행",
use_container_width=True
)

# =====================================================

# MAIN

# =====================================================

if run:

```
with st.spinner("뉴스 수집 중..."):

    articles = collect_news()

st.success(
    f"{len(articles)}개 기사 수집 완료"
)

with st.spinner("AI 분석 중..."):

    result = analyze_articles(articles)

if not result:
    st.stop()

# =================================================
# EXECUTIVE RADAR
# =================================================

st.header("📊 Executive Radar")

signals = result.get(
    "signals",
    {}
)

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

# =================================================
# AI BRIEF
# =================================================

st.header("🧠 AI Brief")

st.info(
    result.get(
        "brief",
        "No summary available."
    )
)

# =================================================
# RISK ALERT
# =================================================

st.header("🚨 Risk Alerts")

alerts = result.get(
    "risk_alerts",
    []
)

if alerts:

    for alert in alerts:

        st.warning(alert)

else:

    st.success(
        "No major risk alerts."
    )

# =================================================
# PENSION MAP
# =================================================

st.header(
    "🏦 Pension Allocation Map"
)

portfolio = [
    {
        "Institution":"CalPERS",
        "PE":"High",
        "Credit":"Medium",
        "Infra":"High",
        "RE":"Low",
        "Secondaries":"Medium"
    },
    {
        "Institution":"CPP",
        "PE":"High",
        "Credit":"High",
        "Infra":"High",
        "RE":"Low",
        "Secondaries":"Medium"
    },
    {
        "Institution":"APG",
        "PE":"Medium",
        "Credit":"Medium",
        "Infra":"High",
        "RE":"Medium",
        "Secondaries":"Low"
    },
    {
        "Institution":"AustralianSuper",
        "PE":"High",
        "Credit":"Medium",
        "Infra":"High",
        "RE":"Medium",
        "Secondaries":"Low"
    },
    {
        "Institution":"GPIF",
        "PE":"Medium",
        "Credit":"Low",
        "Infra":"Medium",
        "RE":"Low",
        "Secondaries":"Low"
    }
]

st.table(portfolio)

# =================================================
# ASSET ISSUE RADAR
# =================================================

st.header("📡 Asset Issue Radar")

issues = result.get(
    "asset_issues",
    []
)

for issue in issues:

    with st.expander(
        issue.get(
            "asset",
            "Asset"
        )
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

# =================================================
# REBALANCING
# =================================================

st.header(
    "🔄 Rebalancing Tracker"
)

rebalancing = result.get(
    "rebalancing",
    []
)

for row in rebalancing:

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

# =================================================
# NEWS
# =================================================

st.header("📰 Latest News")

with st.expander(
    "기사 보기"
):

    for row in articles[:50]:

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
```
