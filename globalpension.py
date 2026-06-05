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
from plotly.subplots import make_subplots
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
        "aum": "1,212.9조원 (2024말)", "aum_usd": 880,
        "fy_end": "Dec 31", "currency": "KRW",
        "description": "세계 3위 규모 공적연금. 보건복지부 산하 공단이 운용. 2040년대 기금 소진 우려로 대체투자 확대 추진 중.",
        "strategy": "대체투자 비중 단계적 확대(목표 17%). 해외 사모·인프라·크레딧 중심. 국내 부동산 비중 축소.",
    },
    "CPPIB": {
        "country": "🇨🇦 Canada", "type": "Sovereign Pension",
        "aum": "C$793.3B (FY2026)", "aum_usd": 587,
        "fy_end": "Mar 31", "currency": "CAD",
        "description": "캐나다 연방 공무원·군인·경찰 연금 운용. 캐나다 5대 연기금 중 최대 규모. 액티브 알파 전략 추구.",
        "strategy": "Private Equity·Credit·Real Assets 각 20% 이상. 미국 비중 확대(48%). 지속가능에너지 인프라 신설.",
    },
    "CalPERS": {
        "country": "🇺🇸 USA", "type": "Public Pension",
        "aum": "$634.6B (FY2025)", "aum_usd": 635,
        "fy_end": "Jun 30", "currency": "USD",
        "description": "미국 최대 주 공무원 연금. 캘리포니아 주정부 직원 약 200만명 대상. 펀딩비율 79%(2025).",
        "strategy": "PE 비중 17%→확대 방향. 사모채권(Private Debt) 신설 카테고리. 리얼에셋 스트림라인.",
    },
    "OTPP": {
        "country": "🇨🇦 Canada", "type": "Teacher Pension",
        "aum": "C$279.4B (2025)", "aum_usd": 207,
        "fy_end": "Dec 31", "currency": "CAD",
        "description": "온타리오주 교원 연금. 13년 연속 완전적립. Venture Growth 카테고리 신설.",
        "strategy": "공모주식 비중 상향(14%→18%). 인프라 축소(17%→13%). Venture Growth 확대(4%→6%).",
    },
    "PSP Investments": {
        "country": "🇨🇦 Canada", "type": "Federal Pension",
        "aum": "C$299.7B (FY2025)", "aum_usd": 222,
        "fy_end": "Mar 31", "currency": "CAD",
        "description": "캐나다 연방 공무원·군인·RCMP 연금. 오타와 본사, 몬트리올·뉴욕·런던·홍콩 오피스.",
        "strategy": "자본시장 48.7%(비중 최대). 크레딧·자연자원 확대. 부동산 오피스 손실 반영 완료.",
    },
}

# 자산배분: {펀드: {자산군: (현재%, 전년%)}}
# ── 출처: 각 기관 연차보고서 원문 (CPPIB FY2026/FY2025재분류, OTPP 2025/2024,
#    CalPERS FY2025/FY2024, PSP FY2025/FY2024). 매핑 규칙은 ALLOC_TS 주석 참조.
ALLOC = {
    # NPS: 연차보고서 기준(2024/2023). 대체 세부비중 = '대체투자 내 비중 × 대체 비중'으로 환산.
    #      PC=사모대출(전술프로그램 내), Infra에 슈퍼코어 인프라 포함,
    #      HF/Other=헤지펀드+멀티에셋, FI에 단기자금·복지부문 포함.
    "국민연금(NPS)": {
        "Private Equity":    (6.3,  5.7),
        "Private Credit":    (0.6,  0.6),
        "Infrastructure":    (4.5,  4.2),
        "Real Estate":       (4.8,  4.7),
        "Hedge Fund/Other":  (0.9,  0.7),
        "Public Equity":    (47.1, 45.2),
        "Fixed Income":     (36.0, 38.8),
    },
    # CPPIB: FY2026부터 부동산·인프라·에너지가 'Real Assets'로 통합 →
    #        RA 섹터구성(부동산29%/인프라46%/에너지25%)으로 분해, 에너지는 Infra에 포함.
    #        전년(FY2025)은 FY2026 보고서의 재분류 비교치 기준.
    "CPPIB": {
        "Private Equity":   (22.0, 25.0),
        "Private Credit":   ( 9.0, 11.0),
        "Infrastructure":   (14.2, 14.9),
        "Real Estate":       (5.8,  6.1),
        "Hedge Fund/Other":  (0.0,  0.0),
        "Public Equity":    (36.0, 28.0),
        "Fixed Income":     (13.0, 15.0),
    },
    # CalPERS: 보유내역(AIR) 시장가치 합산 파생값. Infra에 산림 포함, HF/Other=현금성+파생.
    "CalPERS": {
        "Private Equity":   (15.7, 14.1),
        "Private Credit":   ( 3.4,  2.6),
        "Infrastructure":   ( 3.3,  3.1),
        "Real Estate":       (7.4,  8.5),
        "Hedge Fund/Other":  (3.4,  3.3),
        "Public Equity":    (39.6, 41.3),
        "Fixed Income":     (27.1, 27.2),
    },
    # OTPP: 이펙티브 자산믹스(레버리지 포함, 합계>100%). PE=사모주식+벤처그로스,
    #       FI=채권+실질금리상품, HF/Other=절대수익전략.
    #       원자재·천연자원·인플레헤지·펀딩(-)은 제외.
    "OTPP": {
        "Private Equity":   (25.0, 27.0),
        "Private Credit":   (14.0, 14.0),
        "Infrastructure":   (13.0, 17.0),
        "Real Estate":      (10.0, 11.0),
        "Hedge Fund/Other":  (9.0,  9.0),
        "Public Equity":    (18.0, 14.0),
        "Fixed Income":     (23.0, 30.0),
    },
    # PSP: FI=채권+현금, HF/Other=천연자원+보완포트폴리오.
    "PSP Investments": {
        "Private Equity":   (13.6, 15.3),
        "Private Credit":   (10.1,  9.9),
        "Infrastructure":   (10.7, 13.0),
        "Real Estate":       (8.9, 10.3),
        "Hedge Fund/Other":  (6.5,  6.6),
        "Public Equity":    (26.6, 21.0),
        "Fixed Income":     (23.7, 23.9),
    },
}

ALT_CLASSES  = ["Private Equity","Private Credit","Infrastructure","Real Estate","Hedge Fund/Other"]
ALL_CLASSES  = ["Private Equity","Private Credit","Infrastructure","Real Estate",
                "Hedge Fund/Other","Public Equity","Fixed Income"]

# 5개년 총펀드 순수익률 추이 (%, 각 연차보고서 원문)
# CPPIB·PSP: 3월말 회계연도 / CalPERS: 6월말 / OTPP: 12월말
RETURNS_TS = {
    "국민연금(NPS)": {"2020":9.7,"2021":10.8,"2022":-8.2,"2023":13.6,"2024":15.0},
    "CPPIB":         {"FY2022":6.8,"FY2023":1.3,"FY2024":8.0,"FY2025":9.3,"FY2026":7.8},
    "CalPERS":       {"FY2021":21.3,"FY2022":-6.1,"FY2023":5.8,"FY2024":9.3,"FY2025":11.6},
    "OTPP":          {"2021":11.1,"2022":4.0,"2023":1.9,"2024":9.4,"2025":6.7},
    "PSP Investments":{"FY2021":18.4,"FY2022":10.9,"FY2023":4.4,"FY2024":7.2,"FY2025":12.6},
}

# 1년 벤치마크 수익률 (%, 공시 연도만; CalPERS는 초과성과 bp에서 역산한 파생값)
BENCHMARK_TS = {
    "국민연금(NPS)": {"2020":8.59,"2021":10.82,"2022":-8.07,"2023":14.10,"2024":15.54},  # 금융부문 TWR 기준
    "OTPP":          {"2021":8.8,"2022":2.3,"2023":8.7,"2024":12.9,"2025":11.7},
    "PSP Investments":{"FY2021":16.5,"FY2022":9.4,"FY2023":-2.8,"FY2024":6.4,"FY2025":17.4},
    "CalPERS":       {"FY2022":-7.0,"FY2023":5.55,"FY2025":9.9},
    # CPPIB는 1년 벤치마크 미공시 → 부가가치(VA): FY22 +2.1%p, FY23 +1.3%p, FY26 -5.4%p
}

# 순자산/AUM 시계열 (현지통화 10억 단위, NPS는 조원)
AUM_TS = {
    "국민연금(NPS)": {"2020":833.7,"2021":948.7,"2022":890.5,"2023":1035.8,"2024":1212.9},
    "CPPIB":         {"FY2022":539.3,"FY2023":570.0,"FY2024":632.3,"FY2025":714.4,"FY2026":793.3},
    "OTPP":          {"2021":241.6,"2022":247.2,"2023":247.5,"2024":266.3,"2025":279.4},
    "CalPERS":       {"FY2021":485.0,"FY2022":444.0,"FY2023":465.9,"FY2024":551.4,"FY2025":634.6},
    "PSP Investments":{"FY2021":204.5,"FY2022":230.5,"FY2023":243.7,"FY2024":264.9,"FY2025":299.7},
}

# 자산배분 5개년 시계열 (% of net assets, 7개 자산군 매핑 — 각 연도 보고서 원문 기준)
# 매핑: CPPIB FY2026은 Real Assets를 부동산29%/인프라46%/에너지25%로 분해(에너지→Infra).
#       OTPP는 이펙티브 믹스(레버리지 포함, 합계>100%), PE=사모주식+벤처그로스.
#       PSP FI=채권+현금, HF/Other=천연자원+보완PF. CalPERS는 보유내역 합산 파생값.
ALLOC_TS = {
    # NPS: 대체 세부 = 대체투자 내 비중 × 대체 비중 환산. PC(사모대출)는 '22년부터 분리 공시
    #      ('20~'21은 PE에 포함). HF/Other=헤지펀드+멀티에셋. FI에 단기자금 포함.
    "국민연금(NPS)": {
        "2020": {"Private Equity":4.0,"Private Credit":0.0,"Infrastructure":3.1,"Real Estate":3.8,"Hedge Fund/Other":0.0,"Public Equity":44.3,"Fixed Income":44.7},
        "2021": {"Private Equity":5.0,"Private Credit":0.0,"Infrastructure":3.2,"Real Estate":4.0,"Hedge Fund/Other":0.4,"Public Equity":44.5,"Fixed Income":43.0},
        "2022": {"Private Equity":5.7,"Private Credit":0.5,"Infrastructure":4.3,"Real Estate":5.2,"Hedge Fund/Other":0.7,"Public Equity":41.1,"Fixed Income":42.3},
        "2023": {"Private Equity":5.7,"Private Credit":0.6,"Infrastructure":4.2,"Real Estate":4.7,"Hedge Fund/Other":0.7,"Public Equity":45.2,"Fixed Income":38.8},
        "2024": {"Private Equity":6.3,"Private Credit":0.6,"Infrastructure":4.5,"Real Estate":4.8,"Hedge Fund/Other":0.9,"Public Equity":47.1,"Fixed Income":36.0},
    },
    "CPPIB": {
        "FY2022": {"Private Equity":32,"Private Credit":16,"Infrastructure":9,"Real Estate":9,"Hedge Fund/Other":0,"Public Equity":27,"Fixed Income":7},
        "FY2023": {"Private Equity":33,"Private Credit":13,"Infrastructure":9,"Real Estate":9,"Hedge Fund/Other":0,"Public Equity":24,"Fixed Income":12},
        "FY2024": {"Private Equity":31,"Private Credit":13,"Infrastructure":8,"Real Estate":8,"Hedge Fund/Other":0,"Public Equity":28,"Fixed Income":12},
        "FY2025": {"Private Equity":29,"Private Credit":11,"Infrastructure":9,"Real Estate":7,"Hedge Fund/Other":0,"Public Equity":29,"Fixed Income":15},
        "FY2026": {"Private Equity":22,"Private Credit":9,"Infrastructure":14.2,"Real Estate":5.8,"Hedge Fund/Other":0,"Public Equity":36,"Fixed Income":13},
    },
    "OTPP": {
        "2021": {"Private Equity":26,"Private Credit":10,"Infrastructure":11,"Real Estate":11,"Hedge Fund/Other":6,"Public Equity":11,"Fixed Income":19},
        "2022": {"Private Equity":27,"Private Credit":14,"Infrastructure":16,"Real Estate":12,"Hedge Fund/Other":8,"Public Equity":9,"Fixed Income":35},
        "2023": {"Private Equity":27,"Private Credit":16,"Infrastructure":16,"Real Estate":12,"Hedge Fund/Other":8,"Public Equity":10,"Fixed Income":39},
        "2024": {"Private Equity":27,"Private Credit":14,"Infrastructure":17,"Real Estate":11,"Hedge Fund/Other":9,"Public Equity":14,"Fixed Income":30},
        "2025": {"Private Equity":25,"Private Credit":14,"Infrastructure":13,"Real Estate":10,"Hedge Fund/Other":9,"Public Equity":18,"Fixed Income":23},
    },
    "CalPERS": {
        "FY2021": {"Private Equity":7.9,"Private Credit":0.5,"Infrastructure":1.4,"Real Estate":7.8,"Hedge Fund/Other":7.0,"Public Equity":48.7,"Fixed Income":26.6},
        "FY2022": {"Private Equity":11.0,"Private Credit":1.3,"Infrastructure":2.6,"Real Estate":11.9,"Hedge Fund/Other":10.5,"Public Equity":38.5,"Fixed Income":24.3},
        "FY2023": {"Private Equity":11.9,"Private Credit":2.1,"Infrastructure":3.0,"Real Estate":11.2,"Hedge Fund/Other":5.5,"Public Equity":40.7,"Fixed Income":25.5},
        "FY2024": {"Private Equity":14.1,"Private Credit":2.6,"Infrastructure":3.1,"Real Estate":8.5,"Hedge Fund/Other":3.3,"Public Equity":41.3,"Fixed Income":27.2},
        "FY2025": {"Private Equity":15.7,"Private Credit":3.4,"Infrastructure":3.3,"Real Estate":7.4,"Hedge Fund/Other":3.4,"Public Equity":39.6,"Fixed Income":27.1},
    },
    "PSP Investments": {
        "FY2021": {"Private Equity":15.5,"Private Credit":7.1,"Infrastructure":9.0,"Real Estate":13.1,"Hedge Fund/Other":4.8,"Public Equity":29.4,"Fixed Income":21.0},
        "FY2022": {"Private Equity":15.3,"Private Credit":9.5,"Infrastructure":10.2,"Real Estate":13.5,"Hedge Fund/Other":5.6,"Public Equity":25.7,"Fixed Income":20.2},
        "FY2023": {"Private Equity":15.3,"Private Credit":10.7,"Infrastructure":12.1,"Real Estate":13.1,"Hedge Fund/Other":5.9,"Public Equity":21.9,"Fixed Income":21.0},
        "FY2024": {"Private Equity":15.3,"Private Credit":9.9,"Infrastructure":13.0,"Real Estate":10.3,"Hedge Fund/Other":6.6,"Public Equity":21.0,"Fixed Income":23.9},
        "FY2025": {"Private Equity":13.6,"Private Credit":10.1,"Infrastructure":10.7,"Real Estate":8.9,"Hedge Fund/Other":6.5,"Public Equity":26.6,"Fixed Income":23.7},
    },
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
    "국민연금(NPS)": "2024 수익률 15.0%로 2년 연속 사상 최고. 대체투자 비중 17.1%(206.9조원) 도달. 해외주식 +34.6% 고수익, 국내주식 -7.0% 부진. 인프라 +23.0%·사모 +21.2% 호조.",
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

# CSS  ── 다크 테마 전체 적용
st.markdown("""
<style>
/* ════════════════════════════════
   전체 앱 다크 배경
════════════════════════════════ */
.stApp, [data-testid="stAppViewContainer"] {
    background-color: #0d1117 !important;
}
[data-testid="stAppViewBlockContainer"] {
    background-color: #0d1117 !important;
}
/* 메인 컨텐츠 영역 텍스트 */
.stApp, .stApp * {
    color: #e2e8f0;
}
/* 헤딩 */
h1, h2, h3 { color: #f1f5f9 !important; font-weight: 700 !important; }
h4, h5     { color: #93c5fd !important; font-weight: 700 !important; }

/* ── 사이드바 ── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background-color: #0b1220 !important;
}
[data-testid="stSidebar"] * { color: #dce6f0 !important; }

/* ── 탭 ── */
[data-testid="stTabs"] {
    background-color: transparent !important;
}
[data-testid="stTabs"] button {
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 6px 16px !important;
    color: #64748b !important;
    background: transparent !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #60a5fa !important;
    border-bottom: 2px solid #3b82f6 !important;
}

/* ── 기관 개요 카드 ── */
.metric-card {
    background: #1a2535;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 4px solid #3b82f6;
    margin-bottom: 8px;
    color: #cbd5e1 !important;
    line-height: 1.8;
}
.metric-card b { color: #f1f5f9 !important; }

/* ── 기관 헤더 배너 ── */
.fund-header {
    background: #1a2535;
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 16px;
    border: 1px solid #2d4a6e;
}

/* ── 뱃지 ── */
.badge-alt       { background:#1e3a5f; color:#93c5fd !important; padding:3px 9px; border-radius:5px; font-size:12px; font-weight:600; }
.badge-fund      { background:#14532d; color:#86efac !important; padding:3px 9px; border-radius:5px; font-size:12px; font-weight:600; }
.badge-risk-red  { background:#450a0a; color:#fca5a5 !important; padding:3px 9px; border-radius:5px; font-size:12px; font-weight:600; }
.badge-risk-yel  { background:#422006; color:#fde68a !important; padding:3px 9px; border-radius:5px; font-size:12px; font-weight:600; }
.badge-risk-grn  { background:#14532d; color:#86efac !important; padding:3px 9px; border-radius:5px; font-size:12px; font-weight:600; }

/* ── 구분선 ── */
hr { border-color: #334155 !important; margin: 20px 0 !important; }

/* ── Streamlit 위젯 다크 처리 ── */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div,
[data-testid="stTextInput"] > div {
    background-color: #1a2535 !important;
    color: #e2e8f0 !important;
}
/* expander */
[data-testid="stExpander"] {
    background-color: #141e2e !important;
    border: 1px solid #1e3a5f !important;
}
/* info / warning / success 박스 */
[data-testid="stInfo"]    { background-color: #0c2a4a !important; }
[data-testid="stWarning"] { background-color: #2a1f00 !important; }
[data-testid="stSuccess"] { background-color: #0a2a1a !important; }

/* ── 캡션 ── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #64748b !important;
}
</style>
""", unsafe_allow_html=True)

# ── 차트 공통 레이아웃 헬퍼 ──────────────────────────────────
CHART_BG   = "#1e293b"
PAPER_BG   = "rgba(0,0,0,0)"
GRID_COLOR = "#334155"
TICK_COLOR = "#e2e8f0"
TITLE_COLOR= "#94a3b8"

def norm_year(yr: str) -> str:
    """FY2022 → 2022, 2021 → 2021 (연도 표기 통일)"""
    return yr.replace("FY", "").strip()

def chart_layout(**kwargs):
    """공통 다크 테마 레이아웃"""
    base = dict(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=CHART_BG,
        font=dict(color=TICK_COLOR, size=12),
        xaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(color=TICK_COLOR, size=12), linecolor=GRID_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(color=TICK_COLOR, size=12), linecolor=GRID_COLOR),
        margin=dict(l=10, r=20, t=40, b=10),
    )
    base.update(kwargs)
    return base

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
    st.caption("🌐 글로벌 연기금 규모 순위")
    ranking_html = """
<table style='width:100%;border-collapse:collapse;font-size:11px;color:#cbd5e1'>
<tr style='background:#1a2535;color:#90caf9'>
  <th style='padding:4px 6px;text-align:center'>#</th>
  <th style='padding:4px 6px;text-align:left'>기금명</th>
  <th style='padding:4px 6px;text-align:right'>AUM(B$)</th>
  <th style='padding:4px 6px;text-align:center'>분류</th>
</tr>
<tr style='background:#0d1117'><td style='padding:3px 6px;text-align:center'>1</td><td>🇳🇴 Norway GPFG</td><td style='text-align:right'>1,700</td><td style='text-align:center;color:#aab8c8'>국부펀드</td></tr>
<tr style='background:#111827'><td style='padding:3px 6px;text-align:center'>2</td><td>🇯🇵 Japan GPIF</td><td style='text-align:right'>1,500</td><td style='text-align:center;color:#aab8c8'>공적연금</td></tr>
<tr style='background:#0d1117;border-left:3px solid #3b82f6'><td style='padding:3px 6px;text-align:center'>3</td><td><b style='color:#f8fafc'>🇰🇷 국민연금 ★</b></td><td style='text-align:right'><b>880</b></td><td style='text-align:center;color:#90caf9'>공적연금</td></tr>
<tr style='background:#111827'><td style='padding:3px 6px;text-align:center'>4</td><td>🇸🇬 GIC</td><td style='text-align:right'>770</td><td style='text-align:center;color:#aab8c8'>국부펀드</td></tr>
<tr style='background:#0d1117'><td style='padding:3px 6px;text-align:center'>5</td><td>🇳🇱 ABP</td><td style='text-align:right'>630</td><td style='text-align:center;color:#aab8c8'>직역연금</td></tr>
<tr style='background:#111827;border-left:3px solid #3b82f6'><td style='padding:3px 6px;text-align:center'>6</td><td><b style='color:#f8fafc'>🇺🇸 CalPERS ★</b></td><td style='text-align:right'><b>635</b></td><td style='text-align:center;color:#90caf9'>공적연금</td></tr>
<tr style='background:#0d1117;border-left:3px solid #3b82f6'><td style='padding:3px 6px;text-align:center'>7</td><td><b style='color:#f8fafc'>🇨🇦 CPPIB ★</b></td><td style='text-align:right'><b>587</b></td><td style='text-align:center;color:#90caf9'>공적연금</td></tr>
<tr style='background:#111827'><td style='padding:3px 6px;text-align:center'>8</td><td>🇳🇱 PFZW</td><td style='text-align:right'>320</td><td style='text-align:center;color:#aab8c8'>직역연금</td></tr>
<tr style='background:#0d1117;border-left:3px solid #3b82f6'><td style='padding:3px 6px;text-align:center'>9</td><td><b style='color:#f8fafc'>🇨🇦 PSP ★</b></td><td style='text-align:right'><b>222</b></td><td style='text-align:center;color:#90caf9'>공적연금</td></tr>
<tr style='background:#111827;border-left:3px solid #3b82f6'><td style='padding:3px 6px;text-align:center'>10</td><td><b style='color:#f8fafc'>🇨🇦 OTPP ★</b></td><td style='text-align:right'><b>207</b></td><td style='text-align:center;color:#90caf9'>직역연금</td></tr>
</table>
<p style='font-size:10px;color:#4a5568;margin-top:4px'>★ 본 분석 대상 | 2024~2025 연차보고서 기준</p>
"""
    st.markdown(ranking_html, unsafe_allow_html=True)

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
<b style='font-size:15px;color:#f8fafc'>{fund}</b><br>
<span style='color:#aab8c8;font-size:12px'>{m['country']} | {m['type']}</span><br>
<span style='font-size:13px;color:#cbd5e1'>AUM: <b style='color:#f8fafc'>{m['aum']}</b></span><br>
<span style='font-size:13px;color:#cbd5e1'>대체투자: <b style='color:#90caf9;font-size:15px'>{alt_cur:.1f}%</b>
 <span style='font-size:12px;color:{"#81c995" if delta>0 else "#f48fb1"}'>{dstr}</span></span>
</div>""", unsafe_allow_html=True)

    st.caption("※ OTPP는 레버리지 포함 이펙티브 자산믹스 기준이라 대체투자 비중이 타 기관 대비 높게 표시됨. NPS 대체 세부비중은 보고서 대체투자 구성비에서 환산.")

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
    header_html = "<table style='width:100%;border-collapse:collapse;font-size:14px'>"
    header_html += "<tr style='background:#1a2535'><th style='padding:10px;text-align:left;color:#cbd5e1'>자산군</th>"
    for fund in FUNDS:
        header_html += f"<th style='padding:10px;text-align:center;color:#f8fafc'>{fund}</th>"
    header_html += "<th style='padding:10px;text-align:center;color:#cbd5e1'>자산군 특징</th></tr>"

    is_alt = {a: (a in ALT_CLASSES) for a in ALL_CLASSES}
    for asset in ALL_CLASSES:
        bg = "#111827" if is_alt[asset] else "#0d1117"
        border = "border-left:3px solid #3b82f6;" if is_alt[asset] else ""
        header_html += f"<tr style='background:{bg};{border}'>"
        header_html += f"<td style='padding:10px;font-weight:bold;color:#f1f5f9'>{asset}</td>"
        for fund in FUNDS:
            cur, pre = ALLOC[fund].get(asset, (None, None))
            arrow    = delta_arrow(cur, pre)
            color    = "#90caf9" if is_alt[asset] else "#e2e8f0"
            ac       = "#81c995" if (cur and pre and cur>pre+0.4) else ("#f48fb1" if (cur and pre and cur<pre-0.4) else "#aab8c8")
            cell = f"<b>{pct_badge(cur)}</b><br><span style='font-size:11px;color:{ac}'>{arrow}</span>"
            header_html += f"<td style='padding:10px;text-align:center;color:{color}'>{cell}</td>"
        summ = ASSET_SUMMARY.get(asset,"")[:60]+"…" if len(ASSET_SUMMARY.get(asset,""))>60 else ASSET_SUMMARY.get(asset,"")
        header_html += f"<td style='padding:10px;font-size:12px;color:#8fa3b8'>{summ}</td>"
        header_html += "</tr>"

    # 대체투자 합산 행
    header_html += "<tr style='background:#1e2a3a;border-top:2px solid #3b82f6'>"
    header_html += "<td style='padding:10px;font-weight:bold;color:#90caf9'>대체투자 합계</td>"
    for fund in FUNDS:
        alt_cur = sum(ALLOC[fund][a][0] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[0] is not None)
        alt_pre = sum(ALLOC[fund][a][1] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[1] is not None)
        arr = delta_arrow(alt_cur, alt_pre)
        ac  = "#81c995" if alt_cur>alt_pre+0.2 else ("#f48fb1" if alt_cur<alt_pre-0.2 else "#aab8c8")
        header_html += f"<td style='padding:10px;text-align:center;font-weight:bold;font-size:15px;color:#90caf9'>{alt_cur:.1f}%<br><span style='font-size:11px;color:{ac}'>{arr}</span></td>"
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

    fund_tabs = st.tabs(FUNDS)

    for tab_idx, tab in enumerate(fund_tabs):
        fund = FUNDS[tab_idx]
        meta   = FUND_META[fund]
        alloc  = ALLOC[fund]
        ret_ts = RETURNS_TS[fund]
        issue  = RECENT_ISSUES[fund]

        with tab:
            # 헤더
            st.markdown(f"""
<div class='fund-header'>
<span style='font-size:20px;font-weight:bold;color:#e2e8f0'>{fund}</span>
&nbsp;&nbsp;<span style='color:#94a3b8'>{meta['country']} | {meta['type']} | AUM {meta['aum']}</span>
</div>""", unsafe_allow_html=True)

            # ── 자산배분 가로 막대차트 + 대체투자 카드 ─────────────
            asset_color_map = {
                "Private Equity":"#3b82f6","Private Credit":"#8b5cf6",
                "Infrastructure":"#10b981","Real Estate":"#f59e0b",
                "Hedge Fund/Other":"#6366f1","Public Equity":"#475569","Fixed Income":"#64748b",
            }

            c1, c2 = st.columns([1.4, 1])

            with c1:
                # 전체 자산배분 가로 막대차트
                all_alloc_items = [(a, alloc.get(a,(0,0))) for a in ALL_CLASSES]
                bar_labels = [a for a,_ in all_alloc_items]
                bar_values = [v[0] if v[0] else 0 for _,v in all_alloc_items]
                bar_colors = [asset_color_map.get(a,"#64748b") for a in bar_labels]
                fig_bar = go.Figure(go.Bar(
                    y=bar_labels, x=bar_values,
                    orientation="h",
                    marker_color=bar_colors,
                    text=[f"{v:.1f}%" for v in bar_values],
                    textposition="outside",
                    textfont=dict(size=13, color="#e2e8f0"),
                    cliponaxis=False,
                ))
                fig_bar.update_layout(
                    title=dict(text=f"{fund} 현재 자산배분", font_size=14,
                               font=dict(color="#94a3b8")),
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=13),
                    xaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%",
                               range=[0, max(bar_values)*1.35],
                               tickfont=dict(color=TICK_COLOR, size=11),
                               showgrid=True),
                    yaxis=dict(tickfont=dict(color="#f1f5f9", size=13),
                               categoryorder="array",
                               categoryarray=list(reversed(bar_labels))),
                    margin=dict(l=10, r=70, t=44, b=10),
                    height=310,
                    showlegend=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True, key=f"hbar_{fund}")

            with c2:
                # 대체투자 전기 대비 카드
                st.markdown("<p style='font-size:15px;font-weight:700;color:#90caf9;margin-bottom:12px'>대체투자 비중 변화 (전기 대비)</p>", unsafe_allow_html=True)
                for a in ALT_CLASSES:
                    cur, pre = alloc.get(a,(None,None))
                    if cur is None: continue
                    d = (cur - pre) if pre else 0
                    delta_color_val = "#4ade80" if d>0.2 else ("#f87171" if d<-0.2 else "#94a3b8")
                    delta_icon = "▲" if d>0.2 else ("▼" if d<-0.2 else "→")
                    delta_str = f"{delta_icon} {abs(d):.1f}%p"
                    bar_pct   = min(cur / 30 * 100, 100)
                    ac_color  = asset_color_map.get(a, "#64748b")
                    st.markdown(f"""
<div style='margin-bottom:14px'>
  <div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px'>
    <span style='font-size:13px;font-weight:600;color:#c9d6e3'>{a}</span>
    <span>
      <span style='font-size:16px;font-weight:700;color:#f0f4f8'>{cur:.1f}%</span>
      &nbsp;<span style='font-size:12px;color:{delta_color_val};font-weight:600'>{delta_str}</span>
    </span>
  </div>
  <div style='background:#1e293b;border-radius:4px;height:8px;overflow:hidden'>
    <div style='background:{ac_color};width:{bar_pct:.1f}%;height:100%;border-radius:4px'></div>
  </div>
</div>""", unsafe_allow_html=True)

            st.divider()

            # ── 5개년 대체투자 비중 추이 ───────────────────────────
            st.markdown("##### 📈 대체투자 자산군 5개년 추이")
            alloc_ts_fund = ALLOC_TS.get(fund, {})
            if alloc_ts_fund:
                ts_rows = []
                for yr, yr_alloc in alloc_ts_fund.items():
                    for ac in ALT_CLASSES:
                        ts_rows.append({"연도": norm_year(yr), "자산군": ac, "비중(%)": yr_alloc.get(ac, 0)})
                df_ts = pd.DataFrame(ts_rows)
                alt_color_map = {
                    "Private Equity":"#3b82f6","Private Credit":"#8b5cf6",
                    "Infrastructure":"#10b981","Real Estate":"#f59e0b",
                    "Hedge Fund/Other":"#6366f1",
                }
                fig_ts = px.line(df_ts, x="연도", y="비중(%)", color="자산군",
                                 markers=True,
                                 color_discrete_map=alt_color_map,
                                 title=f"{fund} 대체투자 자산군별 5개년 비중 추이")
                fig_ts.update_layout(
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), legend=dict(font=dict(color=TICK_COLOR, size=11), bgcolor="rgba(0,0,0,0)"),
                    yaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%"),
                    xaxis=dict(gridcolor=GRID_COLOR),
                    hovermode="x unified",
                )
                fig_ts.update_traces(line_width=2)
                st.plotly_chart(fig_ts, use_container_width=True, key=f"ts_{fund}")

                # 대체투자 합계 추이
                ts_total = []
                for yr, yr_alloc in alloc_ts_fund.items():
                    total = sum(yr_alloc.get(ac, 0) for ac in ALT_CLASSES)
                    ts_total.append({"연도": norm_year(yr), "대체투자 합계(%)": round(total, 1)})
                df_total = pd.DataFrame(ts_total)
                fig_total = px.bar(df_total, x="연도", y="대체투자 합계(%)",
                                   text="대체투자 합계(%)",
                                   color="대체투자 합계(%)",
                                   color_continuous_scale=["#1e3a5f","#3b82f6","#90caf9"],
                                   title=f"{fund} 대체투자 합계 비중 5개년 추이")
                fig_total.update_traces(texttemplate="%{text:.1f}%", textposition="outside",
                                        textfont=dict(color="#f1f5f9", size=13))
                fig_total.update_layout(
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), showlegend=False,
                    yaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%",
                               tickfont=dict(color=TICK_COLOR, size=12)),
                    xaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(color=TICK_COLOR, size=12)),
                )
                st.plotly_chart(fig_total, use_container_width=True, key=f"total_{fund}")

            # ── 5개년 전체 자산배분 스택 바 + 리밸런싱 분석 ──────────
            st.markdown("<p style='font-size:16px;font-weight:700;color:#93c5fd;margin:12px 0 6px'>📊 전체 자산배분 5개년 변화</p>", unsafe_allow_html=True)
            alloc_ts_fund2 = ALLOC_TS.get(fund, {})
            if alloc_ts_fund2:
                years2 = [norm_year(yr) for yr in alloc_ts_fund2.keys()]
                raw_years2 = list(alloc_ts_fund2.keys())
                all_cls_order = ["Fixed Income","Public Equity","Hedge Fund/Other",
                                 "Real Estate","Infrastructure","Private Credit","Private Equity"]
                stk_color = {
                    "Private Equity":"#3b82f6","Private Credit":"#8b5cf6",
                    "Infrastructure":"#10b981","Real Estate":"#f59e0b",
                    "Hedge Fund/Other":"#6366f1","Public Equity":"#64748b","Fixed Income":"#374151",
                }
                fig_stk = go.Figure()
                for cls in all_cls_order:
                    vals = [alloc_ts_fund2[yr].get(cls, 0) for yr in raw_years2]
                    fig_stk.add_trace(go.Bar(
                        name=cls, x=years2, y=vals,
                        marker_color=stk_color.get(cls,"#64748b"),
                        hovertemplate=f"<b>{cls}</b><br>%{{y:.1f}}%<extra></extra>",
                        text=[f"{v:.0f}" for v in vals],
                        textposition="inside",
                        textfont=dict(color="#ffffff", size=10),
                    ))
                fig_stk.update_layout(
                    barmode="stack",
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12),
                    legend=dict(orientation="h", yanchor="bottom", y=1.03,
                                xanchor="right", x=1,
                                font=dict(color=TICK_COLOR, size=11),
                                bgcolor="rgba(0,0,0,0)"),
                    yaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%",
                               tickfont=dict(color=TICK_COLOR, size=12)),
                    xaxis=dict(tickfont=dict(color=TICK_COLOR, size=13)),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=320,
                )
                st.plotly_chart(fig_stk, use_container_width=True, key=f"stk_{fund}")

                # ── 리밸런싱 분석 멘트 ──────────────────────────────
                first_yr_raw = raw_years2[0]
                last_yr_raw  = raw_years2[-1]
                first_a = alloc_ts_fund2[first_yr_raw]
                last_a  = alloc_ts_fund2[last_yr_raw]
                changes = {cls: round(last_a.get(cls,0) - first_a.get(cls,0), 1) for cls in ALL_CLASSES}
                top_inc = sorted([(c,d) for c,d in changes.items() if d > 0.3], key=lambda x: -x[1])
                top_dec = sorted([(c,d) for c,d in changes.items() if d < -0.3], key=lambda x: x[1])
                alt_start = sum(first_a.get(c,0) for c in ALT_CLASSES)
                alt_end   = sum(last_a.get(c,0)  for c in ALT_CLASSES)
                alt_delta = round(alt_end - alt_start, 1)
                alt_arrow = "▲" if alt_delta > 0 else "▼"
                alt_color = "#4ade80" if alt_delta > 0 else "#f87171"

                inc_items = "".join(
                    f"<li><b style='color:#60a5fa'>{c}</b>: {first_a.get(c,0):.1f}% → {last_a.get(c,0):.1f}% "
                    f"<span style='color:#4ade80'>(+{d:.1f}%p)</span></li>"
                    for c,d in top_inc
                ) or "<li style='color:#94a3b8'>뚜렷한 확대 자산군 없음</li>"

                dec_items = "".join(
                    f"<li><b style='color:#a78bfa'>{c}</b>: {first_a.get(c,0):.1f}% → {last_a.get(c,0):.1f}% "
                    f"<span style='color:#f87171'>({d:.1f}%p)</span></li>"
                    for c,d in top_dec
                ) or "<li style='color:#94a3b8'>뚜렷한 축소 자산군 없음</li>"

                rebal_html = f"""
<div style='background:#162032;border:1px solid #2d4a6e;border-radius:10px;padding:18px 22px;margin-top:12px'>
  <p style='font-size:15px;font-weight:700;color:#93c5fd;margin:0 0 10px'>
    🔄 리밸런싱 분석 ({norm_year(first_yr_raw)} → {norm_year(last_yr_raw)})
  </p>
  <p style='font-size:13px;color:#e2e8f0;margin:0 0 6px'>
    대체투자 합계: <b style='color:#f1f5f9'>{alt_start:.1f}%</b> →
    <b style='color:{alt_color};font-size:15px'>{alt_end:.1f}%</b>
    &nbsp;<span style='color:{alt_color}'>{alt_arrow} {abs(alt_delta):.1f}%p</span>
  </p>
  <div style='display:flex;gap:24px;margin-top:10px'>
    <div style='flex:1'>
      <p style='font-size:12px;font-weight:700;color:#4ade80;margin:0 0 6px'>📈 비중 확대</p>
      <ul style='margin:0;padding-left:16px;font-size:13px;color:#e2e8f0;line-height:1.9'>{inc_items}</ul>
    </div>
    <div style='flex:1'>
      <p style='font-size:12px;font-weight:700;color:#f87171;margin:0 0 6px'>📉 비중 축소</p>
      <ul style='margin:0;padding-left:16px;font-size:13px;color:#e2e8f0;line-height:1.9'>{dec_items}</ul>
    </div>
  </div>
  <p style='font-size:12px;color:#64748b;margin:10px 0 0'>
    ※ 기관별 회계연도 기준: NPS(12월말)·OTPP(12월말)·CPPIB·PSP(3월말)·CalPERS(6월말)
  </p>
</div>"""
                st.markdown(rebal_html, unsafe_allow_html=True)

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
                fig_ret.update_layout(paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                                      font=dict(color=TICK_COLOR, size=12),showlegend=False,
                                      yaxis=dict(gridcolor=GRID_COLOR),
                                      xaxis=dict(gridcolor=GRID_COLOR))
                st.plotly_chart(fig_ret, use_container_width=True, key=f"ret_{fund}")

            with c4:
                st.markdown("<p style='font-size:15px;font-weight:700;color:#90caf9'>기관 특징</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:13px;color:#c9d6e3;line-height:1.7'>{meta['description']}</p>", unsafe_allow_html=True)
                st.markdown("<p style='font-size:15px;font-weight:700;color:#90caf9;margin-top:12px'>최근 운용 방향</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:13px;color:#c9d6e3;line-height:1.7'>{meta['strategy']}</p>", unsafe_allow_html=True)
                st.markdown("<p style='font-size:15px;font-weight:700;color:#fbbf24;margin-top:12px'>⚡ 최근 이슈</p>", unsafe_allow_html=True)
                st.markdown(f"<div style='background:#1e2a1a;border-left:3px solid #fbbf24;border-radius:4px;padding:10px 14px;font-size:13px;color:#d4e8c2;line-height:1.7'>{issue}</div>", unsafe_allow_html=True)

            # AI 상세 분석
            st.divider()
            if st.button("🧠 AI 기관 분석", key=f"ai_fund_btn_{fund}"):
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

    asset_tabs = st.tabs(ALT_CLASSES)

    for tab_idx, tab in enumerate(asset_tabs):
        asset = ALT_CLASSES[tab_idx]

        with tab:
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
                    # d=0도 표시되도록 is None 체크
                    d_valid = d is not None and not (isinstance(d, float) and np.isnan(d))
                    color = "#4ade80" if (d_valid and d > 0) else ("#f87171" if (d_valid and d < 0) else "#94a3b8")
                    delta_txt = ""
                    if d_valid:
                        sign = "▲ +" if d > 0 else ("▼ " if d < 0 else "→ ")
                        delta_txt = f"<span style='color:{color};font-weight:600'>{sign}{abs(d):.1f}%p</span>"
                    rank_html = (
                        f"<div style='display:flex;justify-content:space-between;align-items:center;"
                        f"padding:6px 0;border-bottom:1px solid #1e293b'>"
                        f"<span style='color:#94a3b8;font-size:12px;min-width:28px'><b style='color:#f1f5f9'>{int(row['순위'])}</b>위</span>"
                        f"<span style='flex:1;padding:0 8px;font-size:13px;font-weight:600;color:#f1f5f9'>{row['기관']}</span>"
                        f"<span style='font-size:15px;font-weight:700;color:#60a5fa'>{pct_badge(cur)}</span>"
                        f"&nbsp;&nbsp;{delta_txt}</div>"
                    )
                    st.markdown(rank_html, unsafe_allow_html=True)

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
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), xaxis_title="비중 (%)",
                    xaxis=dict(gridcolor=GRID_COLOR), yaxis=dict(gridcolor=GRID_COLOR),
                    height=300,
                )
                st.plotly_chart(fig, use_container_width=True, key=f"bar_{asset}")

            st.divider()

            # 전기 대비 비교 차트
            st.markdown(f"##### 전기 대비 증감 비교")
            df_delta = df_rank.dropna(subset=["증감(pp)"]).copy()
            fig2 = px.bar(df_delta, x="기관", y="증감(pp)",
                          color="증감(pp)", color_continuous_scale=["#f48fb1","#94a3b8","#81c995"],
                          text="증감(pp)")
            fig2.update_traces(texttemplate="%{text:+.1f}pp", textposition="outside")
            fig2.update_layout(paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                               font=dict(color=TICK_COLOR, size=12),showlegend=False,
                               yaxis=dict(gridcolor=GRID_COLOR))
            st.plotly_chart(fig2, use_container_width=True, key=f"delta_{asset}")

            st.divider()

            # ── 5개년 기관별 비중 추이 ──────────────────────────────
            st.markdown(f"##### 📈 {asset} – 기관별 5개년 비중 추이")
            fund_color_map = {
                "국민연금(NPS)":"#f59e0b","CPPIB":"#3b82f6",
                "CalPERS":"#10b981","OTPP":"#8b5cf6","PSP Investments":"#f43f5e",
            }
            ts5_rows = []
            for f in FUNDS:
                alloc_ts_f = ALLOC_TS.get(f, {})
                for yr, yr_alloc in alloc_ts_f.items():
                    val = yr_alloc.get(asset)
                    if val is not None:
                        ts5_rows.append({"연도": norm_year(yr), "기관": f, "비중(%)": val})
            if ts5_rows:
                df_ts5 = pd.DataFrame(ts5_rows)
                fig_ts5 = px.line(df_ts5, x="연도", y="비중(%)", color="기관",
                                  markers=True,
                                  color_discrete_map=fund_color_map,
                                  title=f"{asset} 기관별 5개년 비중 변화")
                fig_ts5.update_layout(
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), legend=dict(font=dict(color=TICK_COLOR, size=11), bgcolor="rgba(0,0,0,0)"),
                    yaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%"),
                    xaxis=dict(gridcolor=GRID_COLOR),
                    hovermode="x unified",
                )
                fig_ts5.update_traces(line_width=2.5)
                st.plotly_chart(fig_ts5, use_container_width=True, key=f"ts5_{asset}")

                # 연도별 기관 비중 요약표 (히트맵)
                df_pivot = df_ts5.pivot(index="기관", columns="연도", values="비중(%)")
                df_pivot = df_pivot.reindex([f for f in FUNDS if f in df_pivot.index])
                # 연도 정렬
                sorted_cols = sorted(df_pivot.columns, key=lambda x: int(x))
                df_pivot = df_pivot[sorted_cols]

                st.markdown(
                    "<p style='font-size:14px;font-weight:700;color:#93c5fd;margin:14px 0 4px'>"
                    "📋 연도별 비중 요약표 "
                    "<span style='font-size:11px;font-weight:400;color:#64748b'>"
                    "— 셀 색상이 짙을수록 해당 연도 비중이 높음. 행=기관, 열=연도</span></p>",
                    unsafe_allow_html=True
                )
                fig_heat = go.Figure(go.Heatmap(
                    z=df_pivot.values.tolist(),
                    x=list(df_pivot.columns),
                    y=list(df_pivot.index),
                    colorscale=[[0,"#1e293b"],[0.5,"#2563eb"],[1,"#93c5fd"]],
                    text=[[f"{v:.1f}%" if (v == v) else "–"   # NaN check
                           for v in row] for row in df_pivot.values],
                    texttemplate="%{text}",
                    textfont=dict(size=13, color="#ffffff"),
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="%", font=dict(color=TICK_COLOR)),
                        tickfont=dict(color=TICK_COLOR),
                        thickness=12, len=0.8,
                    ),
                    hoverongaps=False,
                    hovertemplate="<b>%{y}</b><br>%{x}년<br>비중: <b>%{text}</b><extra></extra>",
                ))
                fig_heat.update_layout(
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), height=240,
                    margin=dict(l=0, r=60, t=30, b=10),
                    xaxis=dict(side="top", tickfont=dict(color=TICK_COLOR, size=12)),
                    yaxis=dict(tickfont=dict(color=TICK_COLOR, size=12)),
                )
                st.plotly_chart(fig_heat, use_container_width=True, key=f"heat_{asset}")

            st.divider()

            # 자산군 특징 & 이슈
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
            if st.button("🧠 AI 자산군 비교 분석", key=f"ai_asset_btn_{asset}"):
                data = {f: ALLOC[f].get(asset,(None,None)) for f in FUNDS}
                prompt = f"""분석 자산군: {asset}
기관별 현재/전기 비중: {json.dumps({f:{{"cur":v[0],"pre":v[1]}} for f,v in data.items()}, ensure_ascii=False)}
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
        art_risk     = art["risk"]
        risk_badge   = f"<span class='{risk_cls}'>{art_risk}</span>"

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

            alloc_dr = item.get("allocation",{})

            if alloc_dr:
                st.markdown("**추출된 자산배분 (검수 후 저장)**")
                df_edit = pd.DataFrame({
                    "자산군": list(alloc_dr),
                    "AI 추출 (%)": [round(v,1) for v in alloc_dr.values()],
                    "검수 수정 (%)": [round(v,1) for v in alloc_dr.values()],
                })
                edited = st.data_editor(df_edit, key=f"edit_{item['file']}",
                                        use_container_width=True, hide_index=True)

                if st.button("✅ 대시보드에 반영", key=f"save_{item['file']}"):
                    fund_name = item.get("fund_name","")
                    year      = item.get("report_year","")
                    saved = st.session_state.get("dr_saved",{})
                    saved[(fund_name, year)] = dict(zip(edited["자산군"], edited["검수 수정 (%)"]))
                    st.session_state["dr_saved"] = saved
                    st.success(f"'{fund_name} ({year})' 저장 완료!")

                fig_dr = px.bar(
                    pd.DataFrame({"자산군":list(alloc_dr),"비중(%)":list(alloc_dr.values())}).sort_values("비중(%)",ascending=True),
                    x="비중(%)", y="자산군", orientation="h",
                    title=f"{item.get('fund_name','')} ({item.get('report_year','')}) 추출 배분",
                    text="비중(%)"
                )
                fig_dr.update_traces(texttemplate="%{text:.1f}%", textposition="outside",
                                     textfont=dict(color="#f1f5f9"))
                fig_dr.update_layout(paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                                     font=dict(color=TICK_COLOR, size=12))
                st.plotly_chart(fig_dr, use_container_width=True)
            else:
                st.warning("배분 데이터를 추출하지 못했습니다.")

    saved = st.session_state.get("dr_saved",{})
    if saved:
        st.divider()
        st.markdown("##### ✅ 검수 완료 데이터")
        for (fn, yr), alloc_s in saved.items():
            st.markdown(f"• **{fn} ({yr})** – {len(alloc_s)}개 항목")
