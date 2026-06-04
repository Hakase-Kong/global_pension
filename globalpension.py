"""
Institutional Pension Alt Radar  –  globalpension.py
실행: streamlit run globalpension.py
"""
import os, re, io, json, difflib
import requests, fitz
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from openai import OpenAI

# ══════════════════════════════════════════════════════════════
# 0. 환경
# ══════════════════════════════════════════════════════════════
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
NAVER_CLIENT_ID     = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# ══════════════════════════════════════════════════════════════
# 1. 정적 데이터
# ══════════════════════════════════════════════════════════════

FUNDS = ["국민연금(NPS)", "CPPIB", "CalPERS", "OTPP", "PSP Investments"]

FUND_META = {
    "국민연금(NPS)": {
        "country": "🇰🇷 Korea", "type": "National Pension",
        "aum": "1,150조원 (~$850B USD)", "aum_usd": 850,
        "fy_end": "Dec 31", "currency": "KRW",
        "description": "세계 3위 규모 공적연금. 보건복지부 산하 공단이 운용. 2040년대 기금 소진 우려로 대체투자 확대 추진 중.",
        "strategy": "대체투자 비중 단계적 확대(목표 17%). 해외 사모·인프라·크레딧 중심. 국내 부동산 비중 축소.",
    },
    "CPPIB": {
        "country": "🇨🇦 Canada", "type": "Sovereign Pension",
        "aum": "C$793B", "aum_usd": 587,
        "fy_end": "Mar 31", "currency": "CAD",
        "description": "캐나다 연방 공무원·군인·경찰 연금 운용. 캐나다 5대 연기금 중 최대 규모. 액티브 알파 전략 추구.",
        "strategy": "Private Equity·Credit·Real Assets 각 20% 이상. 미국 비중 확대(48%). 지속가능에너지 인프라 신설.",
    },
    "CalPERS": {
        "country": "🇺🇸 USA", "type": "Public Pension",
        "aum": "$634B", "aum_usd": 634,
        "fy_end": "Jun 30", "currency": "USD",
        "description": "미국 최대 주 공무원 연금. 캘리포니아 주정부 직원 약 200만명 대상. 펀딩비율 79%(2025).",
        "strategy": "PE 비중 17%→확대 방향. 사모채권(Private Debt) 신설 카테고리. 리얼에셋 스트림라인.",
    },
    "OTPP": {
        "country": "🇨🇦 Canada", "type": "Teacher Pension",
        "aum": "C$279B", "aum_usd": 207,
        "fy_end": "Dec 31", "currency": "CAD",
        "description": "온타리오주 교원 연금. 13년 연속 완전적립. Venture Growth 카테고리 신설.",
        "strategy": "공모주식 비중 상향(14%→18%). 인프라 축소(17%→13%). Venture Growth 확대(4%→6%).",
    },
    "PSP Investments": {
        "country": "🇨🇦 Canada", "type": "Federal Pension",
        "aum": "C$300B", "aum_usd": 222,
        "fy_end": "Mar 31", "currency": "CAD",
        "description": "캐나다 연방 공무원·군인·RCMP 연금. 오타와 본사, 몬트리올·뉴욕·런던·홍콩 오피스.",
        "strategy": "자본시장 48.7%(비중 최대). 크레딧·자연자원 확대. 부동산 오피스 손실 반영 완료.",
    },
}

# 자산배분: {펀드: {자산군: (현재%, 전년%)}}
ALLOC = {
    "국민연금(NPS)": {
        "Private Equity":    (5.5,  4.8),
        "Private Credit":    (2.8,  2.1),
        "Infrastructure":    (4.2,  3.9),
        "Real Estate":       (4.0,  4.5),
        "Hedge Fund/Other":  (2.5,  2.4),
        "Public Equity":    (49.5, 50.1),
        "Fixed Income":     (31.5, 32.2),
    },
    "CPPIB": {
        "Private Equity":   (22.0, 29.0),
        "Private Credit":   ( 9.0, 11.0),
        "Infrastructure":   (11.2,  8.7),
        "Real Estate":       (5.0,  6.8),
        "Hedge Fund/Other":  (2.0,  None),
        "Public Equity":    (36.0, 29.0),
        "Fixed Income":     (13.0, 15.0),
    },
    "CalPERS": {
        "Private Equity":   (15.6, 13.0),
        "Private Credit":   ( 3.4,  1.5),
        "Infrastructure":   ( 3.3,  3.0),
        "Real Estate":       (7.4,  8.5),
        "Hedge Fund/Other":  (0.0,  0.0),
        "Public Equity":    (38.4, 42.0),
        "Fixed Income":     (27.0, 28.0),
    },
    "OTPP": {
        "Private Equity":   (19.0, 23.0),
        "Private Credit":   ( 0.0,  0.0),
        "Infrastructure":   (13.0, 17.0),
        "Real Estate":      (10.0, 11.0),
        "Hedge Fund/Other":  (9.0,  9.0),
        "Public Equity":    (18.0, 14.0),
        "Fixed Income":     (23.0, 30.0),
    },
    "PSP Investments": {
        "Private Equity":   (13.6, 15.3),
        "Private Credit":   (10.1,  9.9),
        "Infrastructure":   (10.7, 13.0),
        "Real Estate":       (8.9, 10.3),
        "Hedge Fund/Other":  (0.0,  0.0),
        "Public Equity":    (48.7, 42.1),
        "Fixed Income":     ( 0.0,  0.0),
    },
}

ALT_CLASSES  = ["Private Equity","Private Credit","Infrastructure","Real Estate","Hedge Fund/Other"]
ALL_CLASSES  = ["Private Equity","Private Credit","Infrastructure","Real Estate",
                "Hedge Fund/Other","Public Equity","Fixed Income"]

# 3~5년 수익률 추이
RETURNS_TS = {
    "국민연금(NPS)": {"2020":9.7,"2021":10.8,"2022":-8.2,"2023":13.6,"2024":7.3},
    "CPPIB":         {"2021":4.0,"2022":6.8,"2023":1.3,"2024":8.0,"2025":9.3},
    "CalPERS":       {"2021":21.3,"2022":-6.1,"2023":8.7,"2024":9.3,"2025":11.6},
    "OTPP":          {"2021":11.0,"2022":4.2,"2023":1.9,"2024":9.4,"2025":6.7},
    "PSP Investments":{"2021":11.7,"2022":8.0,"2023":9.0,"2024":7.2,"2025":12.6},
}

# 자산군별 전략 요약
ASSET_SUMMARY = {
    "Private Equity":  "바이아웃 중심 → 성장형 확대. AI·테크 섹터 집중. 빈티지 분산 전략.",
    "Private Credit":  "직접대출(Direct Lending) 선호도 급증. 금리 고점 수혜. NAV 파이낸싱 주의.",
    "Infrastructure":  "에너지 전환(재생에너지) 중심 확대. 데이터센터·디지털 인프라 신규 타깃.",
    "Real Estate":     "오피스 손실 반영 마무리 단계. 물류·주거형 선호. 아시아 비중 소폭 확대.",
    "Hedge Fund/Other":"절대수익 전략 유지. CTA·매크로 약세. Reinsurance ILS 관심 증가.",
}

RECENT_ISSUES = {
    "국민연금(NPS)": "2024 대체투자 목표비중 17% 설정. 해외 크레딧 신규 위탁운용사 선정 추진. 국내 부동산 손실 반영 지속.",
    "CPPIB":         "FY2026 7.8% 순수익. 지속가능에너지(Sust. Energy) +23.2%. Active Equities -$3.5B 손실.",
    "CalPERS":       "FY2025 11.6% 수익률, 벤치마크 +1.7%p 초과. 펀딩비율 79% 개선. PE 목표비중 상향 논의.",
    "OTPP":          "2025 6.7% 수익(벤치마크 -5.0%p). Private Equity -5.3% 언더퍼폼. Venture Growth +30.2%.",
    "PSP Investments":"FY2025 12.6% 수익률. 5년 10.6%. 부동산 오피스 손실 마무리. 자본시장 비중 48.7% 확대.",
}

# 뉴스 키워드
NEWS_KEYWORDS = {
    "국민연금(NPS)":   ["국민연금","NPS Korea","국민연금공단"],
    "CPPIB":           ["CPP Investments","CPPIB","Canada Pension"],
    "CalPERS":         ["CalPERS","California pension"],
    "OTPP":            ["Ontario Teachers","OTPP"],
    "PSP Investments": ["PSP Investments","Public Sector Pension"],
}
ASSET_KEYWORDS = {
    "Private Equity":  ["private equity","buyout","PE fund","사모펀드","바이아웃"],
    "Private Credit":  ["private credit","direct lending","private debt","사모대출","크레딧"],
    "Infrastructure":  ["infrastructure","인프라","데이터센터","재생에너지","data center"],
    "Real Estate":     ["real estate","부동산","리츠","REIT","오피스"],
    "Hedge Fund/Other":["hedge fund","헤지펀드","absolute return","CTA"],
}

# ══════════════════════════════════════════════════════════════
# 2. 헬퍼
# ══════════════════════════════════════════════════════════════

def delta_arrow(cur, prev):
    if prev is None or cur is None: return ""
    d = cur - prev
    if   d >  0.5: return f"▲ +{d:.1f}%p"
    elif d < -0.5: return f"▼ {d:.1f}%p"
    else:          return f"→ {d:+.1f}%p"

def delta_color(cur, prev):
    if prev is None or cur is None: return "color:gray"
    d = cur - prev
    if d >  0.5: return "color:#276221;font-weight:bold"
    if d < -0.5: return "color:#9c0006;font-weight:bold"
    return "color:gray"

def pct_badge(v):
    if v is None: return "–"
    return f"{v:.1f}%"

def clean_html(t):
    return re.sub(r"<.*?>","",t) if t else ""

def tag_article(title, desc):
    """기관·자산군 자동 태깅"""
    text = (title+" "+desc).lower()
    fund_tags, asset_tags = [], []
    for fund, kws in NEWS_KEYWORDS.items():
        if any(k.lower() in text for k in kws): fund_tags.append(fund)
    for asset, kws in ASSET_KEYWORDS.items():
        if any(k.lower() in text for k in kws): asset_tags.append(asset)
    return fund_tags, asset_tags

def risk_level(title, desc):
    text = (title+" "+desc).lower()
    high_kw = ["loss","손실","위기","risk","default","fraud","liquidat","파산"]
    mid_kw  = ["concern","우려","하락","decline","pressure","축소"]
    if any(k in text for k in high_kw): return "🔴 High"
    if any(k in text for k in mid_kw):  return "🟡 Medium"
    return "🟢 Low"

# ══════════════════════════════════════════════════════════════
# 3. API
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def fetch_news(keywords):
    if not NAVER_CLIENT_ID: return []
    articles, seen = [], set()
    for kw in keywords:
        try:
            r = requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={"X-Naver-Client-Id":NAVER_CLIENT_ID,
                         "X-Naver-Client-Secret":NAVER_CLIENT_SECRET},
                params={"query":kw,"display":10,"sort":"date"},timeout=15)
            for item in r.json().get("items",[]):
                lnk = item.get("originallink","")
                if lnk not in seen:
                    seen.add(lnk)
                    articles.append({
                        "title":clean_html(item.get("title","")),
                        "description":clean_html(item.get("description","")),
                        "link":lnk, "pubDate":item.get("pubDate",""),
                    })
        except: pass
    return articles

def ai_call(prompt, model="gpt-4o-mini"):
    if not client: return None
    try:
        r = client.chat.completions.create(
            model=model, response_format={"type":"json_object"},
            messages=[{"role":"user","content":prompt}])
        return json.loads(r.choices[0].message.content)
    except Exception as e:
        st.error(f"AI 오류: {e}"); return None

# ══════════════════════════════════════════════════════════════
# 4. PDF 추출 (Data Room)
# ══════════════════════════════════════════════════════════════

ALLOC_KW = ["asset mix","asset allocation","net investments","% of net assets",
            "fixed income","private equity","infrastructure","real estate",
            "as at december","as at march","as at june"]

def extract_pages(uploaded_file, max_p=8, max_c=12000):
    try:
        b = uploaded_file.read()
        doc = fitz.open(stream=io.BytesIO(b), filetype="pdf")
        del b
        scored = []
        for i, page in enumerate(doc):
            t = page.get_text() or ""
            score = sum(1 for k in ALLOC_KW if k in t.lower())
            score += min(len(re.findall(r'\d+\.?\d*\s*%',t)),15)
            if i<3: score+=3
            scored.append((score,i,t))
        top = sorted(sorted(scored,key=lambda x:-x[0])[:max_p],key=lambda x:x[1])
        doc.close()
        return "\n\n---\n\n".join(f"[P{i+1}]\n{t}" for _,i,t in top)[:max_c]
    except Exception as e:
        return f"오류: {e}"

def ai_extract_pdf(file):
    fname = file.name
    text  = extract_pages(file)
    if not text or not client: return None
    prompt = f"""Pension annual report '{fname}'. Extract allocation table. Return JSON:
{{
  "fund_name":"<name>","report_year":"<year>","prior_year":"<year or null>",
  "summary":"<80 words>",
  "allocation":{{"<asset class>":<pct float>}},
  "prior_allocation":{{"<asset class>":<pct float>}},
  "allocation_found":true/false
}}
Rules: leaf-level rows only, exclude negatives, include ALL rows.
PAGES:\n{text}"""
    return ai_call(prompt, model="gpt-4o")

# ══════════════════════════════════════════════════════════════
# 5. AI 분석
# ══════════════════════════════════════════════════════════════

def ai_main_interpretation(matrix_json):
    if not client: return None
    prompt = f"""You are a CIO advisor for a Korean institutional investor.
Analyze the following pension fund allocation matrix and return ONLY JSON:
{{
  "headline": "<2-sentence executive summary in Korean>",
  "pe_signal": "<PE trend signal, Korean, 1 sentence>",
  "credit_signal": "<Private Credit signal, Korean>",
  "infra_signal": "<Infrastructure signal, Korean>",
  "re_signal": "<Real Estate signal, Korean>",
  "key_movers": ["<fund: what changed and why, Korean>"],
  "opportunity": "<top opportunity for Korean insurer, Korean>",
  "risk": "<main risk, Korean>"
}}
MATRIX: {json.dumps(matrix_json, ensure_ascii=False)}"""
    return ai_call(prompt)

def ai_fund_detail(fund, meta, alloc, returns, issue):
    if not client: return None
    prompt = f"""Analyze this pension fund and return ONLY JSON:
{{
  "characteristics": "<3 key distinguishing features, Korean>",
  "alt_strategy": "<alternative investment strategy direction, Korean, 2-3 sentences>",
  "performance_comment": "<recent performance analysis, Korean>",
  "outlook": "<12-month outlook, Korean>"
}}
FUND: {fund}
META: {json.dumps(meta, ensure_ascii=False)}
ALLOCATION: {json.dumps(alloc, ensure_ascii=False)}
RETURNS: {json.dumps(returns, ensure_ascii=False)}
ISSUE: {issue}"""
    return ai_call(prompt)

def ai_news_summary(title, desc):
    if not client: return "–"
    prompt = f"""Summarize in 3 Korean bullet points (each ≤20 chars):
TITLE: {title}
CONTENT: {desc}
Return JSON: {{"bullets": ["•...", "•...", "•..."]}}"""
    r = ai_call(prompt)
    if r: return "\n".join(r.get("bullets",[]))
    return "–"

# ══════════════════════════════════════════════════════════════
# 6. 페이지 CONFIG
# ══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Institutional Pension Alt Radar",
    layout="wide", page_icon="📡",
    initial_sidebar_state="expanded"
)

# CSS
st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #0f1923; }
[data-testid="stSidebar"] * { color: #e8edf2 !important; }
.metric-card {
    background:#1a2535; border-radius:10px; padding:16px 18px;
    border-left:4px solid #3b82f6; margin-bottom:8px;
}
.fund-header {
    background:linear-gradient(90deg,#1a2535,#0f1923);
    border-radius:8px; padding:14px 20px; margin-bottom:12px;
}
.badge-alt  { background:#1e3a5f; color:#90caf9; padding:2px 8px; border-radius:4px; font-size:12px; }
.badge-fund { background:#1b3a2d; color:#81c995; padding:2px 8px; border-radius:4px; font-size:12px; }
.badge-risk-red  { background:#4a1515; color:#f48fb1; padding:2px 8px; border-radius:4px; font-size:12px; }
.badge-risk-yel  { background:#3a2e00; color:#fff176; padding:2px 8px; border-radius:4px; font-size:12px; }
.badge-risk-grn  { background:#1b3a2d; color:#a5d6a7; padding:2px 8px; border-radius:4px; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# 7. SIDEBAR 네비게이션
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 📡 Pension Alt Radar")
    st.markdown("---")
    page = st.radio("", [
        "🏠 Radar 메인",
        "🏦 기관별 상세",
        "📊 자산군별 비교",
        "📰 News · Issues · Deals",
        "📁 Data Room",
    ], label_visibility="collapsed")
    st.markdown("---")
    st.caption("분석 대상")
    for f in FUNDS:
        st.markdown(f"• {f}")
    st.caption("분석 자산군")
    for a in ALT_CLASSES:
        st.markdown(f"• {a}")

# ══════════════════════════════════════════════════════════════
# PAGE 1: RADAR 메인
# ══════════════════════════════════════════════════════════════

if page == "🏠 Radar 메인":
    st.title("📡 Institutional Pension Alt Radar")
    st.caption("대체투자 배분 매트릭스 · AI 종합 해석 · Pension Flow Map")

    # ── 기관 개요 카드 ──────────────────────────────────────
    st.subheader("기관 개요 비교")
    cols = st.columns(len(FUNDS))
    for i, fund in enumerate(FUNDS):
        m = FUND_META[fund]
        alt_cur = sum(v[0] for k,v in ALLOC[fund].items() if k in ALT_CLASSES)
        alt_pre = sum(v[1] for k,v in ALLOC[fund].items() if k in ALT_CLASSES and v[1] is not None)
        delta = alt_cur - alt_pre
        dstr  = f"{'▲' if delta>0 else '▼'} {abs(delta):.1f}%p" if abs(delta)>0.1 else "→"
        with cols[i]:
            st.markdown(f"""
<div class='metric-card'>
<b style='font-size:14px'>{fund}</b><br>
<span style='color:#94a3b8;font-size:12px'>{m['country']} | {m['type']}</span><br>
<span style='font-size:13px'>AUM: <b>{m['aum']}</b></span><br>
<span style='font-size:13px'>대체투자: <b style='color:#90caf9'>{alt_cur:.1f}%</b>
 <span style='font-size:11px;color:{"#81c995" if delta>0 else "#f48fb1"}'>{dstr}</span></span>
</div>""", unsafe_allow_html=True)

    st.divider()

    # ── 배분 매트릭스 ───────────────────────────────────────
    st.subheader("🗺 Pension Fund Flow Map – 배분 매트릭스")

    matrix_rows = []
    for asset in ALL_CLASSES:
        row = {"자산군": asset}
        for fund in FUNDS:
            cur, pre = ALLOC[fund].get(asset, (None, None))
            row[fund] = cur
            row[f"{fund}_delta"] = delta_arrow(cur, pre)
        matrix_rows.append(row)
    df_matrix = pd.DataFrame(matrix_rows).set_index("자산군")

    # 표 렌더링
    header_html = "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
    header_html += "<tr style='background:#1a2535'><th style='padding:8px;text-align:left;color:#94a3b8'>자산군</th>"
    for fund in FUNDS:
        header_html += f"<th style='padding:8px;text-align:center;color:#e2e8f0'>{fund}</th>"
    header_html += "<th style='padding:8px;text-align:center;color:#94a3b8'>자산군 특징</th></tr>"

    is_alt = {a: (a in ALT_CLASSES) for a in ALL_CLASSES}
    for asset in ALL_CLASSES:
        bg = "#111827" if is_alt[asset] else "#0d1117"
        border = "border-left:3px solid #3b82f6;" if is_alt[asset] else ""
        header_html += f"<tr style='background:{bg};{border}'>"
        header_html += f"<td style='padding:8px;font-weight:bold;color:#e2e8f0'>{asset}</td>"
        for fund in FUNDS:
            cur, pre = ALLOC[fund].get(asset, (None, None))
            arrow    = delta_arrow(cur, pre)
            color    = "#90caf9" if is_alt[asset] else "#e2e8f0"
            ac       = "#81c995" if (cur and pre and cur>pre+0.4) else ("#f48fb1" if (cur and pre and cur<pre-0.4) else "#94a3b8")
            cell = f"{pct_badge(cur)}<br><span style='font-size:10px;color:{ac}'>{arrow}</span>"
            header_html += f"<td style='padding:8px;text-align:center;color:{color}'>{cell}</td>"
        summ = ASSET_SUMMARY.get(asset,"")[:60]+"…" if len(ASSET_SUMMARY.get(asset,""))>60 else ASSET_SUMMARY.get(asset,"")
        header_html += f"<td style='padding:8px;font-size:11px;color:#64748b'>{summ}</td>"
        header_html += "</tr>"

    # 대체투자 합산 행
    header_html += "<tr style='background:#1e2a3a;border-top:2px solid #3b82f6'>"
    header_html += "<td style='padding:8px;font-weight:bold;color:#90caf9'>대체투자 합계</td>"
    for fund in FUNDS:
        alt_cur = sum(ALLOC[fund][a][0] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[0] is not None)
        alt_pre = sum(ALLOC[fund][a][1] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[1] is not None)
        arr = delta_arrow(alt_cur, alt_pre)
        ac  = "#81c995" if alt_cur>alt_pre+0.2 else ("#f48fb1" if alt_cur<alt_pre-0.2 else "#94a3b8")
        header_html += f"<td style='padding:8px;text-align:center;font-weight:bold;color:#90caf9'>{alt_cur:.1f}%<br><span style='font-size:10px;color:{ac}'>{arr}</span></td>"
    header_html += "<td></td></tr></table>"

    st.markdown(header_html, unsafe_allow_html=True)

    # ── AI 해석 카드 ────────────────────────────────────────
    st.divider()
    st.subheader("🧠 AI 종합 해석")

    if st.button("AI 분석 실행", key="ai_main"):
        matrix_json = {f: {a: ALLOC[f].get(a,(None,None))[0] for a in ALT_CLASSES} for f in FUNDS}
        with st.spinner("AI 분석 중..."):
            result = ai_main_interpretation(matrix_json)
        if result:
            st.session_state["ai_main_result"] = result

    ai_r = st.session_state.get("ai_main_result")
    if ai_r:
        st.info(f"**📌 헤드라인:** {ai_r.get('headline','')}")
        c1,c2 = st.columns(2)
        with c1:
            for k,label in [("pe_signal","Private Equity"),("credit_signal","Private Credit"),
                            ("infra_signal","Infrastructure"),("re_signal","Real Estate")]:
                st.markdown(f"**{label}:** {ai_r.get(k,'')}")
        with c2:
            st.markdown(f"**🎯 기회:** {ai_r.get('opportunity','')}")
            st.markdown(f"**⚠️ 리스크:** {ai_r.get('risk','')}")
            for m in ai_r.get("key_movers",[]):
                st.markdown(f"• {m}")
    else:
        st.caption("'AI 분석 실행' 버튼을 클릭하면 AI 종합 해석이 표시됩니다.")

    # ── 최근 이슈 코멘트 ────────────────────────────────────
    st.divider()
    st.subheader("💬 최근 이슈 코멘트")
    for fund in FUNDS:
        with st.expander(f"**{fund}**"):
            st.write(RECENT_ISSUES[fund])

# ══════════════════════════════════════════════════════════════
# PAGE 2: 기관별 상세
# ══════════════════════════════════════════════════════════════

elif page == "🏦 기관별 상세":
    st.title("🏦 기관별 상세")

    fund = st.selectbox("기관 선택", FUNDS, key="fund_detail")
    meta   = FUND_META[fund]
    alloc  = ALLOC[fund]
    ret_ts = RETURNS_TS[fund]
    issue  = RECENT_ISSUES[fund]

    # 헤더
    st.markdown(f"""
<div class='fund-header'>
<span style='font-size:20px;font-weight:bold;color:#e2e8f0'>{fund}</span>
&nbsp;&nbsp;<span style='color:#94a3b8'>{meta['country']} | {meta['type']} | AUM {meta['aum']}</span>
</div>""", unsafe_allow_html=True)

    c1, c2 = st.columns([1.2, 1])

    with c1:
        # 자산배분 도넛
        cur_alloc = {a: v[0] for a,v in alloc.items() if v[0] and v[0]>0}
        df_pie = pd.DataFrame({"자산군":list(cur_alloc),"비중":list(cur_alloc.values())})
        color_map = {
            "Private Equity":"#3b82f6","Private Credit":"#8b5cf6",
            "Infrastructure":"#10b981","Real Estate":"#f59e0b",
            "Hedge Fund/Other":"#6366f1","Public Equity":"#64748b","Fixed Income":"#94a3b8",
        }
        fig_pie = px.pie(df_pie, values="비중", names="자산군",
                         title=f"{fund} 자산배분 (현재)",
                         color="자산군", color_discrete_map=color_map,
                         hole=0.4)
        fig_pie.update_layout(paper_bgcolor="#0d1117",plot_bgcolor="#0d1117",
                              font_color="#e2e8f0",legend_font_size=11)
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        # 대체투자 전기 대비 변화
        st.markdown("##### 대체투자 비중 변화 (전기 대비)")
        for a in ALT_CLASSES:
            cur, pre = alloc.get(a,(None,None))
            if cur is None: continue
            d = (cur - pre) if pre else 0
            color = "#81c995" if d>0.2 else ("#f48fb1" if d<-0.2 else "#94a3b8")
            bar_w = max(int(cur*3), 2)
            st.markdown(
                f"**{a}** &nbsp; `{pct_badge(cur)}` "
                f"<span style='color:{color}'>{delta_arrow(cur,pre)}</span>",
                unsafe_allow_html=True)
            st.progress(min(int(cur)/30, 1.0))

    st.divider()

    # 수익률 추이 & 기관 특징
    c3, c4 = st.columns([1.2, 1])

    with c3:
        st.markdown("##### 3~5년 수익률 추이 (%)")
        df_ret = pd.DataFrame({"연도":list(ret_ts),"수익률(%)":list(ret_ts.values())})
        fig_ret = px.bar(df_ret, x="연도", y="수익률(%)",
                         color="수익률(%)", color_continuous_scale=["#f48fb1","#94a3b8","#81c995"],
                         text="수익률(%)")
        fig_ret.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_ret.update_layout(paper_bgcolor="#0d1117",plot_bgcolor="#111827",
                              font_color="#e2e8f0",showlegend=False,
                              yaxis=dict(gridcolor="#1e293b"),
                              xaxis=dict(gridcolor="#1e293b"))
        st.plotly_chart(fig_ret, use_container_width=True)

    with c4:
        st.markdown("##### 기관 특징")
        st.write(meta["description"])
        st.markdown("##### 최근 운용 방향")
        st.write(meta["strategy"])
        st.markdown("##### 최근 이슈")
        st.warning(issue)

    # AI 상세 분석
    st.divider()
    if st.button("🧠 AI 기관 분석", key="ai_fund"):
        with st.spinner(f"{fund} AI 분석 중..."):
            r = ai_fund_detail(fund, meta,
                               {a:v[0] for a,v in alloc.items()},
                               ret_ts, issue)
        if r: st.session_state[f"ai_fund_{fund}"] = r

    ai_fd = st.session_state.get(f"ai_fund_{fund}")
    if ai_fd:
        st.markdown(f"**특징:** {ai_fd.get('characteristics','')}")
        st.markdown(f"**대체투자 전략:** {ai_fd.get('alt_strategy','')}")
        st.markdown(f"**성과 코멘트:** {ai_fd.get('performance_comment','')}")
        st.markdown(f"**향후 전망:** {ai_fd.get('outlook','')}")

    # 관련 뉴스
    st.divider()
    st.markdown("##### 📰 관련 뉴스")
    kws = NEWS_KEYWORDS.get(fund,[])
    with st.spinner("뉴스 수집 중..."):
        arts = fetch_news(kws[:2])
    for a in arts[:5]:
        with st.expander(a["title"]):
            st.write(a["description"])
            if a["link"]: st.markdown(f"[원문]({a['link']})")

# ══════════════════════════════════════════════════════════════
# PAGE 3: 자산군별 비교
# ══════════════════════════════════════════════════════════════

elif page == "📊 자산군별 비교":
    st.title("📊 자산군별 비교")

    asset = st.selectbox("자산군 선택", ALT_CLASSES, key="asset_compare")

    # 비중 순위 테이블
    rows = []
    for fund in FUNDS:
        cur, pre = ALLOC[fund].get(asset,(None,None))
        rows.append({
            "기관": fund,
            "현재 비중": cur,
            "전기 비중": pre,
            "증감(pp)": round(cur-pre, 1) if cur and pre else None,
            "대체투자 내 비중": round(cur / sum(ALLOC[fund][a][0] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[0]) * 100, 1) if cur else None,
        })
    df_rank = pd.DataFrame(rows).sort_values("현재 비중", ascending=False)
    df_rank["순위"] = range(1, len(df_rank)+1)

    c1, c2 = st.columns([1, 1.4])

    with c1:
        st.markdown(f"##### {asset} – 기관별 비중 순위")
        for _, row in df_rank.iterrows():
            cur = row["현재 비중"]
            d   = row["증감(pp)"]
            color = "#81c995" if (d and d>0) else ("#f48fb1" if (d and d<0) else "#94a3b8")
            st.markdown(
                f"**{int(row['순위'])}위 {row['기관']}** &nbsp; "
                f"`{pct_badge(cur)}` "
                f"<span style='color:{color}'>"
                f"{'▲+' if d and d>0 else ('▼' if d and d<0 else '→')}{abs(d):.1f}%p</span>" if d else "",
                unsafe_allow_html=True)
            if cur:
                st.progress(min(cur/25.0, 1.0))

    with c2:
        # 수평 막대차트
        df_plot = df_rank.dropna(subset=["현재 비중"]).copy()
        df_plot["색상"] = df_plot["증감(pp)"].apply(
            lambda d: "#81c995" if (d and d>0.2) else ("#f48fb1" if (d and d<-0.2) else "#94a3b8"))
        fig = go.Figure(go.Bar(
            x=df_plot["현재 비중"], y=df_plot["기관"],
            orientation="h",
            marker_color=df_plot["색상"].tolist(),
            text=[f"{v:.1f}%" for v in df_plot["현재 비중"]],
            textposition="outside",
        ))
        fig.update_layout(
            title=f"{asset} 비중 순위",
            paper_bgcolor="#0d1117", plot_bgcolor="#111827",
            font_color="#e2e8f0", xaxis_title="비중 (%)",
            xaxis=dict(gridcolor="#1e293b"), yaxis=dict(gridcolor="#1e293b"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 전기 대비 비교 차트
    st.markdown(f"##### 전기 대비 증감 비교")
    df_delta = df_rank.dropna(subset=["증감(pp)"]).copy()
    fig2 = px.bar(df_delta, x="기관", y="증감(pp)",
                  color="증감(pp)", color_continuous_scale=["#f48fb1","#94a3b8","#81c995"],
                  text="증감(pp)")
    fig2.update_traces(texttemplate="%{text:+.1f}pp", textposition="outside")
    fig2.update_layout(paper_bgcolor="#0d1117",plot_bgcolor="#111827",
                       font_color="#e2e8f0",showlegend=False,
                       yaxis=dict(gridcolor="#1e293b"))
    st.plotly_chart(fig2, use_container_width=True)

    # 자산군 특징 & 이슈
    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### 자산군 특징")
        st.info(ASSET_SUMMARY.get(asset,""))
    with c4:
        st.markdown("##### 기관별 전략 방향")
        for fund in FUNDS:
            cur, pre = ALLOC[fund].get(asset,(None,None))
            d = (cur-pre) if cur and pre else 0
            direction = "📈 확대" if d>0.5 else ("📉 축소" if d<-0.5 else "➡ 유지")
            st.markdown(f"**{fund}**: {pct_badge(cur)} {direction}")

    # AI 비교 코멘트
    st.divider()
    if st.button("🧠 AI 자산군 비교 분석", key="ai_asset"):
        data = {f: ALLOC[f].get(asset,(None,None)) for f in FUNDS}
        prompt = f"""분석 자산군: {asset}
기관별 현재/전기 비중: {json.dumps({f:{"cur":v[0],"pre":v[1]} for f,v in data.items()}, ensure_ascii=False)}
전략 특징: {ASSET_SUMMARY.get(asset,"")}
JSON 반환:
{{"leader":"<선도 기관>","laggard":"<뒤처지는 기관>","trend":"<전반적 트렌드 Korean>",
"opportunity":"<한국 기관투자자 관점 기회 Korean>","caution":"<주의사항 Korean>"}}"""
        with st.spinner("AI 분석 중..."):
            r = ai_call(prompt)
        if r: st.session_state[f"ai_asset_{asset}"] = r

    ai_ar = st.session_state.get(f"ai_asset_{asset}")
    if ai_ar:
        st.markdown(f"**선도 기관:** {ai_ar.get('leader','')} &nbsp;|&nbsp; **주의 기관:** {ai_ar.get('laggard','')}")
        st.markdown(f"**트렌드:** {ai_ar.get('trend','')}")
        st.success(f"🎯 **기회:** {ai_ar.get('opportunity','')}")
        st.warning(f"⚠️ **주의:** {ai_ar.get('caution','')}")

# ══════════════════════════════════════════════════════════════
# PAGE 4: News · Issues · Deals
# ══════════════════════════════════════════════════════════════

elif page == "📰 News · Issues · Deals":
    st.title("📰 News · Issues · Deals")
    st.caption("기관·자산군 자동 태깅 | 리스크 레벨 | AI 3줄 요약")

    # 필터
    c1, c2, c3 = st.columns(3)
    with c1: fund_filter  = st.multiselect("기관 필터", ["전체"]+FUNDS, default=["전체"])
    with c2: asset_filter = st.multiselect("자산군 필터", ["전체"]+ALT_CLASSES, default=["전체"])
    with c3: risk_filter  = st.multiselect("리스크 필터", ["전체","🔴 High","🟡 Medium","🟢 Low"], default=["전체"])

    # 뉴스 수집
    all_kws = []
    for kws in NEWS_KEYWORDS.values(): all_kws.extend(kws[:1])
    for kws in ASSET_KEYWORDS.values(): all_kws.extend(kws[:1])

    if st.button("🔄 뉴스 새로고침"):
        st.cache_data.clear()

    with st.spinner("뉴스 수집 중..."):
        articles = fetch_news(all_kws)

    if not articles:
        st.info("Naver API 키가 없으면 뉴스가 표시되지 않습니다.")

    # 태깅 & 필터링
    tagged = []
    for a in articles:
        ftags, atags = tag_article(a["title"], a["description"])
        risk = risk_level(a["title"], a["description"])
        tagged.append({**a, "fund_tags":ftags, "asset_tags":atags, "risk":risk})

    def passes(art):
        if "전체" not in fund_filter  and not any(f in art["fund_tags"]  for f in fund_filter):  return False
        if "전체" not in asset_filter and not any(a in art["asset_tags"] for a in asset_filter): return False
        if "전체" not in risk_filter  and art["risk"] not in risk_filter: return False
        return True

    filtered = [a for a in tagged if passes(a)]
    st.caption(f"총 {len(filtered)}건 (전체 {len(tagged)}건)")

    for art in filtered[:30]:
        risk_cls = {"🔴 High":"badge-risk-red","🟡 Medium":"badge-risk-yel","🟢 Low":"badge-risk-grn"}.get(art["risk"],"badge-risk-grn")
        fund_badges  = " ".join(f"<span class='badge-fund'>{f}</span>"  for f in art["fund_tags"])
        asset_badges = " ".join(f"<span class='badge-alt'>{a}</span>"   for a in art["asset_tags"])
        risk_badge   = f"<span class='{risk_cls}'>{art['risk']}</span>"

        with st.expander(f"{art['title'][:80]}…" if len(art["title"])>80 else art["title"]):
            st.markdown(f"{fund_badges} {asset_badges} {risk_badge}", unsafe_allow_html=True)
            st.write(art["description"])
            c_sum, c_link = st.columns([3,1])
            with c_sum:
                if st.button("AI 3줄 요약", key=f"sum_{art['title'][:30]}"):
                    with st.spinner():
                        summ = ai_news_summary(art["title"], art["description"])
                    st.markdown(summ)
            with c_link:
                if art["link"]: st.markdown(f"[원문 보기]({art['link']})")

# ══════════════════════════════════════════════════════════════
# PAGE 5: Data Room
# ══════════════════════════════════════════════════════════════

elif page == "📁 Data Room":
    st.title("📁 Data Room")
    st.caption("PDF 업로드 → AI 수치 추출 → 사람 검수 → 대시보드 반영")

    uploaded = st.file_uploader("정기보고서 PDF 업로드 (다수 가능)",
                                type=["pdf"], accept_multiple_files=True)

    if uploaded:
        if st.button("🤖 AI 수치 추출", key="dr_extract"):
            extracted = []
            prog = st.progress(0)
            for i, f in enumerate(uploaded):
                with st.spinner(f"추출 중: {f.name}"):
                    r = ai_extract_pdf(f)
                    if r: extracted.append({"file":f.name, **r})
                prog.progress((i+1)/len(uploaded))
            prog.empty()
            st.session_state["dr_extracted"] = extracted
            st.success(f"{len(extracted)}개 파일 추출 완료")

    extracted = st.session_state.get("dr_extracted",[])

    for item in extracted:
        with st.expander(f"📄 {item['file']}  →  {item.get('fund_name','')} ({item.get('report_year','')})"):
            st.markdown(f"**요약:** {item.get('summary','')}")

            alloc = item.get("allocation",{})
            prior = item.get("prior_allocation",{})

            if alloc:
                st.markdown("**추출된 자산배분 (검수 후 저장)**")
                df_edit = pd.DataFrame({
                    "자산군": list(alloc),
                    "AI 추출 (%)": [round(v,1) for v in alloc.values()],
                    "검수 수정 (%)": [round(v,1) for v in alloc.values()],
                })
                edited = st.data_editor(df_edit, key=f"edit_{item['file']}",
                                        use_container_width=True, hide_index=True)

                if st.button("✅ 대시보드에 반영", key=f"save_{item['file']}"):
                    fund_name = item.get("fund_name","")
                    year      = item.get("report_year","")
                    # session_state에 저장 (향후 확장 가능)
                    saved = st.session_state.get("dr_saved",{})
                    saved[(fund_name, year)] = dict(zip(edited["자산군"], edited["검수 수정 (%)"]))
                    st.session_state["dr_saved"] = saved
                    st.success(f"'{fund_name} ({year})' 저장 완료! 기관별 상세 탭에서 확인하세요.")

                # 시각화
                fig = px.bar(
                    pd.DataFrame({"자산군":list(alloc),"비중(%)":list(alloc.values())}).sort_values("비중(%)",ascending=True),
                    x="비중(%)", y="자산군", orientation="h",
                    title=f"{item.get('fund_name','')} ({item.get('report_year','')}) 추출 배분",
                    text="비중(%)"
                )
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig.update_layout(paper_bgcolor="#0d1117",plot_bgcolor="#111827",font_color="#e2e8f0")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("배분 데이터를 추출하지 못했습니다.")

    # 저장된 검수 데이터 목록
    saved = st.session_state.get("dr_saved",{})
    if saved:
        st.divider()
        st.markdown("##### ✅ 검수 완료 데이터")
        for (fn, yr), alloc in saved.items():
            st.markdown(f"• **{fn} ({yr})** – {len(alloc)}개 항목")
