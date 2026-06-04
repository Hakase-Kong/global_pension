"""
globalpension.py – Global Pension Intelligence Platform
실행: streamlit run globalpension.py
"""

import os, re, io, json, base64, difflib
import requests
import fitz
import pandas as pd
import streamlit as st
import plotly.express as px
from openai import OpenAI

# ══════════════════════════════════════════════════════════════
# STATIC DATA  (16개 보고서 기준)
# ══════════════════════════════════════════════════════════════

STATIC_ALLOCATION = {
    ("CPP Investments",    "FY2025"): {"상장주식":29,"사모주식":29,"채권/FI":15,"부동산":7,"인프라":9,"크레딧":11},
    ("CPP Investments",    "FY2026"): {"상장주식":36,"사모주식":22,"채권/FI":13,"크레딧":9,"실물자산":20},
    ("OTPP",               "2024"):   {"상장주식":14,"사모주식":23,"Venture":4,"채권/FI":30,"부동산":11,"인프라":17,"크레딧":14,"ARS":9},
    ("OTPP",               "2025"):   {"상장주식":18,"사모주식":19,"Venture":6,"채권/FI":23,"부동산":10,"인프라":13,"크레딧":14,"ARS":9,"인플레민감":20},
    ("PSP Investments",    "FY2024"): {"상장주식":21,"사모주식":15.3,"채권/FI":21.2,"부동산":10.3,"인프라":13.0,"크레딧":9.9,"자연자원":6.6},
    ("PSP Investments",    "FY2025"): {"사모주식":13.6,"부동산":8.9,"인프라":10.7,"크레딧":10.1,"자본시장":48.7},
    ("NZ Super Fund",      "FY2024"): {"상장주식":46,"사모주식":3,"채권/FI":21,"부동산":5,"인프라":5,"대체":7,"농지/임업":5,"현금":4},
    ("NZ Super Fund",      "FY2025"): {"상장주식":50,"사모주식":5,"채권/FI":18,"부동산":5,"인프라":4,"대체":8,"농지/임업":5,"현금":1},
    ("CDPQ",               "2024"):   {"상장주식":27.5,"사모주식":19.1,"금리":10.3,"크레딧":21.7,"부동산":8.9,"인프라":13.6,"단기":0.9},
    ("CDPQ (La Caisse)",   "2025"):   {"상장주식":29.2,"사모주식":16.4,"금리":10.2,"크레딧":23.3,"부동산":8.3,"인프라":14.4,"단기":0.6},
    ("Future Fund",        "FY2024"): {"선진국주식":20.8,"신흥국주식":6.2,"호주주식":10.3,"사모주식":14.5,"부동산":5.4,"인프라":9.9,"크레딧":11.0,"대체":15.2,"현금":6.7},
    ("Future Fund",        "FY2025"): {"선진국주식":25.8,"신흥국주식":5.7,"호주주식":10.8,"사모주식":13.3,"부동산":4.4,"인프라":11.4,"크레딧":8.9,"대체":14.7,"현금":5.1},
    ("GPFG (Norway)",      "2024"):   {"주식":71.4,"채권/FI":26.6,"비상장 RE":1.8,"신재생에너지인프라":0.1},
    ("GPFG (Norway)",      "2025"):   {"주식":71.3,"채권/FI":26.5,"비상장 RE":1.7,"신재생에너지인프라":0.4},
    ("CalPERS",            "FY2025"): {"국내주식":25.8,"해외주식":12.6,"사모주식":15.6,"채권/FI":27.0,"부동산":7.4,"인프라":3.3,"현금":3.4},
}

STATIC_GEO = {
    ("CPP Investments",  "FY2025"): {"미국":47,"캐나다":12,"유럽":19,"아시아태평양":17,"중남미":5},
    ("CPP Investments",  "FY2026"): {"미국":48,"캐나다":12,"유럽":17,"아시아태평양":18,"중남미":5},
    ("OTPP",             "2025"):   {"미국":38,"캐나다":31,"유럽":18,"아시아태평양":8,"중남미":5},
    ("PSP Investments",  "FY2025"): {"미국":40.5,"캐나다":20.0,"유럽":16.3,"아시아태평양":11.3,"오세아니아":5.5,"기타":6.4},
    ("NZ Super Fund",    "FY2024"): {"북미":54.1,"뉴질랜드":10.6,"유럽":19.6,"아시아태평양":7.9,"호주":3.8,"기타":4.0},
    ("NZ Super Fund",    "FY2025"): {"북미":57.1,"뉴질랜드":11.3,"유럽":18.1,"아시아태평양":8.1,"호주":2.4,"기타":3.0},
    ("CDPQ",             "2024"):   {"미국":38,"캐나다":30,"유럽":15,"아시아태평양":10,"중남미":4,"기타":3},
    ("CDPQ (La Caisse)", "2025"):   {"미국":38,"캐나다":29,"유럽":17,"아시아태평양":10,"중남미":4,"기타":2},
    ("Future Fund",      "FY2024"): {"미국":43,"호주":21,"유럽(영국 제외)":11,"영국":4,"일본":6,"개발도상국":4,"신흥국":10},
    ("Future Fund",      "FY2025"): {"미국":43,"호주":23,"유럽(영국 제외)":11,"영국":4,"일본":6,"개발도상국":4,"신흥국":10},
    ("GPFG (Norway)",    "2024"):   {"미국":53.4,"유럽":25.2,"일본":6.2,"영국":5.5,"기타 아시아":2.5,"오세아니아":2.0,"기타":5.2},
    ("GPFG (Norway)",    "2025"):   {"미국":52.9,"유럽":25.8,"일본":6.0,"영국":5.5,"기타 아시아":2.9,"오세아니아":1.9,"기타":5.0},
}

STATIC_RETURNS = {
    ("CPP Investments",  "FY2025"): {"총 펀드":9.3,"상장주식":10.6,"사모주식":11.8,"채권/FI":8.1,"부동산":3.8,"인프라":9.4,"크레딧":14.4},
    ("CPP Investments",  "FY2026"): {"총 펀드":7.8,"상장주식":17.5,"사모주식":2.9,"채권/FI":-0.1,"부동산":3.7,"인프라":11.2,"크레딧":3.7,"실물자산":12.2},
    ("OTPP",             "2025"):   {"총 펀드":6.7,"상장주식":15.0,"사모주식":-5.3,"채권/FI":2.6,"부동산":-3.1,"인프라":1.8,"크레딧":5.8},
    ("PSP Investments",  "FY2024"): {"총 펀드":7.2,"상장주식":17.5,"사모주식":12.1,"채권/FI":2.9,"부동산":-15.9,"인프라":14.3,"크레딧":14.2},
    ("PSP Investments",  "FY2025"): {"총 펀드":12.6},
    ("NZ Super Fund",    "FY2024"): {"총 펀드":14.9,"Reference Portfolio":15.13},
    ("NZ Super Fund",    "FY2025"): {"총 펀드":11.84,"Reference Portfolio":10.87},
    ("CDPQ",             "2024"):   {"총 펀드":9.4,"상장주식":25.5,"사모주식":17.2,"채권/FI":1.8,"부동산":-10.8,"인프라":9.5,"크레딧":0.8},
    ("CDPQ (La Caisse)", "2025"):   {"총 펀드":9.3,"상장주식":17.7,"사모주식":2.3,"채권/FI":0.5,"부동산":0.2,"인프라":9.2,"크레딧":9.6},
    ("Future Fund",      "FY2024"): {"총 펀드":9.1},
    ("Future Fund",      "FY2025"): {"총 펀드":12.2},
    ("GPFG (Norway)",    "2024"):   {"총 펀드":13.09,"주식":18.19,"채권/FI":1.28,"비상장 RE":-0.57,"인프라":-9.81},
    ("GPFG (Norway)",    "2025"):   {"총 펀드":15.11,"주식":19.29,"채권/FI":5.42,"비상장 RE":4.36,"인프라":18.07},
    ("CalPERS",          "FY2025"): {"총 펀드":11.6,"상장주식":16.8,"사모주식":14.3,"채권/FI":6.5,"부동산":2.8,"크레딧":12.8},
}

STATIC_MULTIYEAR = [
    {"fund":"CPP Investments","year":"FY2026","currency":"CAD","1년":7.8,"전년":9.3,"5년":6.6,"10년":8.8,"설정이후":None},
    {"fund":"CPP Investments","year":"FY2025","currency":"CAD","1년":9.3,"전년":8.0,"5년":9.0,"10년":8.3,"설정이후":None},
    {"fund":"OTPP",           "year":"2025", "currency":"CAD","1년":6.7,"전년":9.4,"5년":6.6,"10년":6.8,"설정이후":9.2},
    {"fund":"PSP Investments","year":"FY2025","currency":"CAD","1년":12.6,"전년":7.2,"5년":10.6,"10년":8.2,"설정이후":None},
    {"fund":"PSP Investments","year":"FY2024","currency":"CAD","1년":7.2,"전년":None,"5년":7.9,"10년":8.3,"설정이후":None},
    {"fund":"NZ Super Fund",  "year":"FY2025","currency":"NZD","1년":11.84,"전년":14.9,"5년":11.62,"10년":10.06,"설정이후":10.09},
    {"fund":"NZ Super Fund",  "year":"FY2024","currency":"NZD","1년":14.9,"전년":12.6,"5년":9.52,"10년":10.33,"설정이후":10.00},
    {"fund":"CDPQ",           "year":"2025", "currency":"CAD","1년":9.3,"전년":9.4,"5년":6.5,"10년":7.2,"설정이후":None},
    {"fund":"CDPQ",           "year":"2024", "currency":"CAD","1년":9.4,"전년":7.2,"5년":6.2,"10년":7.1,"설정이후":None},
    {"fund":"Future Fund",    "year":"FY2025","currency":"AUD","1년":12.2,"전년":9.1,"5년":9.4,"10년":8.0,"설정이후":7.9},
    {"fund":"Future Fund",    "year":"FY2024","currency":"AUD","1년":9.1,"전년":8.2,"5년":6.7,"10년":8.3,"설정이후":7.7},
    {"fund":"GPFG (Norway)",  "year":"2025", "currency":"NOK","1년":15.11,"전년":13.09,"5년":8.26,"10년":8.47,"설정이후":6.64},
    {"fund":"GPFG (Norway)",  "year":"2024", "currency":"NOK","1년":13.09,"전년":16.14,"5년":7.44,"10년":7.25,"설정이후":6.34},
    {"fund":"CalPERS",        "year":"FY2025","currency":"USD","1년":11.6,"전년":None,"5년":8.0,"10년":7.1,"설정이후":None},
]

STATIC_FUNDS = sorted(set(k[0] for k in STATIC_ALLOCATION.keys()))

# ══════════════════════════════════════════════════════════════
# 환경설정
# ══════════════════════════════════════════════════════════════

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
NAVER_CLIENT_ID     = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

KEYWORDS = ["CalPERS","CPP Investments","OMERS","APG","AustralianSuper",
            "GPIF","Private Equity","Private Credit","Infrastructure",
            "Secondaries"]

# ══════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════

def clean_html(t):
    return re.sub(r"<.*?>","",t) if t else ""

def pct_color(val):
    """수익률 셀 색상 (pandas Styler.map 호환)"""
    if not isinstance(val, str) or "%" not in val:
        return ""
    try:
        v = float(val.replace("%","").replace("+",""))
        if v > 10:  return "background-color:#c6efce;color:#276221"
        if v > 0:   return "background-color:#ebf5eb;color:#276221"
        if v < 0:   return "background-color:#ffc7ce;color:#9c0006"
    except: pass
    return ""

def fmt_pct(v, sign=False):
    if v is None: return "–"
    return (f"{v:+.1f}%" if sign else f"{v:.1f}%")

# ══════════════════════════════════════════════════════════════
# 정적 데이터 통합 표 생성
# ══════════════════════════════════════════════════════════════

def build_allocation_table(selected_funds):
    """선택 펀드들의 자산배분 비교표 (asset class × fund/year)"""
    cols, data = [], {}
    for (fund, year), alloc in STATIC_ALLOCATION.items():
        if fund not in selected_funds:
            continue
        col = f"{fund}\n({year})"
        cols.append(col)
        for asset, pct in alloc.items():
            data.setdefault(asset, {})[col] = pct
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(data).T.reindex(columns=cols)
    df = df.applymap(lambda v: f"{v:.1f}%" if pd.notna(v) else "–")
    return df

def build_geo_table(selected_funds):
    cols, data = [], {}
    for (fund, year), geo in STATIC_GEO.items():
        if fund not in selected_funds:
            continue
        col = f"{fund}\n({year})"
        cols.append(col)
        for region, pct in geo.items():
            data.setdefault(region, {})[col] = pct
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(data).T.reindex(columns=cols)
    df = df.applymap(lambda v: f"{v:.1f}%" if pd.notna(v) else "–")
    return df

def build_returns_table(selected_funds):
    cols, data = [], {}
    for (fund, year), ret in STATIC_RETURNS.items():
        if fund not in selected_funds:
            continue
        col = f"{fund}\n({year})"
        cols.append(col)
        for asset, pct in ret.items():
            data.setdefault(asset, {})[col] = pct
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(data).T.reindex(columns=cols)
    # 색상을 위해 포맷 전에 복사
    raw = df.copy()
    df_fmt = df.applymap(lambda v: fmt_pct(v, sign=True) if pd.notna(v) else "–")
    return df_fmt, raw

def build_multiyear_table(selected_funds):
    rows = [r for r in STATIC_MULTIYEAR if r["fund"] in selected_funds]
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.rename(columns={"fund":"펀드","year":"연도","currency":"통화",
                             "1년":"1년(%)","전년":"전년(%)","5년":"5년(연환,%)",
                             "10년":"10년(연환,%)","설정이후":"설정이후(%)"})
    ret_cols = ["1년(%)","전년(%)","5년(연환,%)","10년(연환,%)","설정이후(%)"]
    for c in ret_cols:
        df[c] = df[c].apply(lambda v: f"{v:.1f}%" if pd.notna(v) and v is not None else "–")
    return df.set_index(["펀드","연도"])

# ══════════════════════════════════════════════════════════════
# PDF 분석 (기존 로직 유지)
# ══════════════════════════════════════════════════════════════

ALLOC_KEYWORDS = [
    "asset mix","asset allocation","asset class","portfolio mix","investment mix",
    "net investments","% of net assets","as at december","as at march","as at june",
    "fixed income","private equity","real assets","inflation sensitive",
    "absolute return strategies","public equity","private credit","infrastructure",
    "total portfolio","net assets","equity",
]
HIGH_VALUE_KEYWORDS = [
    "asset mix","asset allocation","net investments","% of net assets",
    "as at december","as at march","as at june","strategic portfolio",
    "portfolio breakdown","asset class",
]
ASSET_CANONICAL = {
    "public equity":"Public Equity","public equities":"Public Equity",
    "listed equity":"Public Equity","listed equities":"Public Equity",
    "global equity":"Public Equity","global equities":"Public Equity",
    "private equity":"Private Equity","private equities":"Private Equity",
    "venture growth":"Venture Growth","venture capital":"Venture Growth",
    "equity":"Equity","equities":"Equity",
    "fixed income":"Fixed Income","fixed-income":"Fixed Income",
    "fixed income securities":"Fixed Income","bonds":"Fixed Income",
    "government bonds":"Fixed Income","rates":"Fixed Income",
    "unlisted infrastructure":"Infrastructure","listed infrastructure":"Infrastructure",
    "infrastructure":"Infrastructure","infra":"Infrastructure",
    "real assets":"Real Assets",
    "unlisted real estate":"Real Estate","listed real estate":"Real Estate",
    "real estate":"Real Estate","property":"Real Estate",
    "credit investments":"Credit","private credit":"Private Credit",
    "private debt":"Private Credit","credit":"Credit",
    "inflation sensitive":"Inflation Sensitive","inflation-sensitive":"Inflation Sensitive",
    "inflation hedge":"Inflation Hedge","commodities":"Commodities",
    "natural resources":"Natural Resources",
    "absolute return strategies":"Absolute Return","absolute return":"Absolute Return",
    "alternatives":"Alternatives","alternative investments":"Alternatives",
    "hedge funds":"Alternatives",
    "cash and cash equivalents":"Cash","short term investments":"Cash","cash":"Cash",
    "unlisted renewable energy infrastructure":"Renewable Energy Infra",
    "renewable energy infrastructure":"Renewable Energy Infra",
    "renewable energy":"Renewable Energy Infra",
}
SUBTOTAL_PARENTS = {
    "Equity":             ["Public Equity","Private Equity","Venture Growth"],
    "Inflation Sensitive":["Commodities","Natural Resources","Inflation Hedge"],
    "Real Assets":        ["Real Estate","Infrastructure","Renewable Energy Infra"],
    "Alternatives":       ["Absolute Return","Private Credit"],
}

def normalize_asset_name(raw):
    key = re.sub(r"[^a-z0-9 ]","",raw.lower()).strip()
    if key in ASSET_CANONICAL: return ASSET_CANONICAL[key]
    for k in sorted(ASSET_CANONICAL,key=len,reverse=True):
        if k in key or key in k: return ASSET_CANONICAL[k]
    return raw.strip().title()

def remove_subtotals(alloc):
    drop = set()
    for parent,children in SUBTOTAL_PARENTS.items():
        if parent in alloc and any(c in alloc for c in children):
            drop.add(parent)
    return {k:v for k,v in alloc.items() if k not in drop}

def get_top_pages_text(uploaded_file, max_pages=8, max_chars=12000):
    try:
        byt = uploaded_file.read()
        doc = fitz.open(stream=io.BytesIO(byt), filetype="pdf")
        del byt
        scored = []
        for i,page in enumerate(doc):
            t = page.get_text() or ""
            tl = t.lower()
            score  = sum(1 for kw in ALLOC_KEYWORDS if kw in tl)
            score += sum(3 for kw in HIGH_VALUE_KEYWORDS if kw in tl)
            score += min(len(re.findall(r'\d+\.?\d*\s*%',t)),15)
            if i<3: score+=3
            if score>0: scored.append((score,i,t))
        scored.sort(key=lambda x:-x[0])
        top = sorted(scored[:max_pages],key=lambda x:x[1])
        combined = "\n\n--- PAGE BREAK ---\n\n".join(
            f"[Page {idx+1}]\n{txt}" for _,idx,txt in top)
        doc.close()
        return combined[:max_chars]
    except Exception as e:
        st.warning(f"텍스트 추출 실패: {e}"); return ""

def summarize_pdf(uploaded_file):
    if not client: return "","","",{},"",{}
    filename = uploaded_file.name
    page_text = get_top_pages_text(uploaded_file)
    if not page_text.strip():
        return f"[{filename}] (추출 실패)\n", filename,"",{},"",{}
    prompt = f"""Below are selected pages from a pension fund annual report (filename: '{filename}').
Find the PRIMARY asset allocation table and return ONLY this JSON:
{{
  "fund_name": "<full official fund name>",
  "report_year": "<most recent fiscal year, 4-digit string>",
  "prior_year": "<prior year if present, else null>",
  "summary": "<100-word summary>",
  "allocation_source": "<table/section name>",
  "allocation": {{"<asset class>": <% as float>}},
  "prior_allocation": {{"<asset class>": <% as float>}},
  "allocation_found": true/false
}}
Rules: leaf-level rows only, exclude negatives, extract ALL rows.
PAGES:
{page_text}"""
    try:
        res = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type":"json_object"},
            messages=[{"role":"user","content":prompt}]
        )
        d = json.loads(res.choices[0].message.content)
        fund_name = d.get("fund_name", filename)
        year      = str(d.get("report_year",""))
        prior_year= str(d.get("prior_year","") or "")
        summary   = d.get("summary","")
        alloc_src = d.get("allocation_source","")
        def build(raw):
            out={}
            for k,v in raw.items():
                try: val=float(v)
                except: continue
                if val<=0: continue
                canon=normalize_asset_name(k)
                out[canon]=out.get(canon,0)+val
            return remove_subtotals(out)
        allocation      = build(d.get("allocation",{}))
        prior_allocation= build(d.get("prior_allocation",{})) if d.get("prior_allocation") else {}
        total = sum(allocation.values())
        if not d.get("allocation_found") or not allocation or total<30:
            st.warning(f"⚠️ '{filename}': 배분 데이터 확인 실패")
            allocation={}; prior_allocation={}
        else:
            note = f" (합계 {total:.1f}%)" if not (90<=total<=110) else ""
            with st.expander(f"📋 '{filename}' 추출 내역{note}"):
                st.caption(f"출처: {alloc_src or '-'}")
                st.json({k:f"{v:.1f}%" for k,v in allocation.items()})
                if prior_allocation and prior_year:
                    st.write(f"**{prior_year}년:**")
                    st.json({k:f"{v:.1f}%" for k,v in prior_allocation.items()})
    except Exception as e:
        st.warning(f"'{filename}' 분석 실패: {e}")
        return f"[{filename}] 실패\n",filename,"",{},"",{}
    label = f"{fund_name} ({year})" if year else fund_name
    return f"[{label}]\n{summary}", fund_name, year, allocation, prior_year, prior_allocation

# ══════════════════════════════════════════════════════════════
# 펀드명 정규화  (CDPQ / CDPQ(La Caisse) 오탐 방지)
# ══════════════════════════════════════════════════════════════

def normalize_fund_name(new_name, existing_names, threshold=0.80):
    if not existing_names: return new_name
    def clean(s): return re.sub(r"[^a-z0-9 ]","",s.lower()).strip()
    _STRIP = ["investment board","investments","investment","pension plan",
              "pension fund","pension","capital","asset management"]
    def core(s):
        t=clean(s)
        for sfx in _STRIP:
            if t.endswith(sfx): t=t[:-len(sfx)].strip()
        return t
    cn=clean(new_name); co=core(new_name)
    best,best_s=None,0.0
    for name in existing_names:
        ce=clean(name); oe=core(name)
        # substring 허용: 짧은 쪽이 긴 쪽 길이의 75% 이상일 때만
        for a,b in [(cn,ce),(co,oe)]:
            if a and b and (a in b or b in a):
                shorter,longer=sorted([len(a),len(b)])
                if longer>0 and shorter/longer>=0.75:
                    return name
        score=max(
            difflib.SequenceMatcher(None,cn,ce).ratio(),
            difflib.SequenceMatcher(None,co,oe).ratio() if co and oe else 0,
        )
        if score>best_s: best_s=score; best=name
    return best if best_s>=threshold else new_name

# ══════════════════════════════════════════════════════════════
# 뉴스
# ══════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def collect_news():
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET: return []
    articles,seen=[],set()
    for kw in KEYWORDS:
        try:
            res=requests.get(
                "https://openapi.naver.com/v1/search/news.json",
                headers={"X-Naver-Client-Id":NAVER_CLIENT_ID,
                         "X-Naver-Client-Secret":NAVER_CLIENT_SECRET},
                params={"query":kw,"display":10,"sort":"date"},timeout=20)
            for item in res.json().get("items",[]):
                lnk=item.get("originallink","")
                if lnk not in seen:
                    seen.add(lnk)
                    articles.append({"keyword":kw,"title":clean_html(item.get("title","")),
                                     "description":clean_html(item.get("description","")),
                                     "link":lnk})
        except: pass
    return articles

# ══════════════════════════════════════════════════════════════
# AI 분석
# ══════════════════════════════════════════════════════════════

def analyze_intelligence(articles, report_summaries=""):
    if not client: return None
    news_text="\n".join([f"- {x['title']} | {x['description']}" for x in articles[:50]])
    prompt=f"""You are CIO advisor for a Korean insurance company.
Analyze the pension report summaries and news, return ONLY this JSON:
{{
 "signals":{{"Private Equity":"","Private Credit":"","Infrastructure":"","Real Estate":"","Secondaries":""}},
 "brief":"","opportunities":[],"risk_alerts":[],"implications":""
}}
PENSION SUMMARIES:\n{report_summaries or "(none)"}
NEWS:\n{news_text}"""
    try:
        res=client.chat.completions.create(
            model="gpt-4o-mini",response_format={"type":"json_object"},
            messages=[{"role":"user","content":prompt}])
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        st.error(f"OpenAI Error: {e}"); return None

# ══════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════

st.set_page_config(page_title="Global Pension Intelligence",layout="wide",page_icon="🌍")
st.title("🌍 Global Pension Intelligence Platform")
st.caption("저장된 데이터 열람 + PDF 분석 + AI 인텔리전스")

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("📚 기관 데이터 열람")
    selected_static = st.multiselect(
        "기관 선택 (전체 = 미선택)",
        options=STATIC_FUNDS, default=[],
        help="저장된 16개 보고서 데이터"
    )
    view_funds = selected_static if selected_static else STATIC_FUNDS

    st.divider()
    st.header("⚙️ AI 분석 설정")
    uploaded_reports = st.file_uploader(
        "PDF 업로드 (다수 가능)",
        type=["pdf"], accept_multiple_files=True
    )
    run_button = st.button("🚀 Run Analysis", use_container_width=True)

# ══════════════════════════════════════════════════════════════
# MAIN TABS
# ══════════════════════════════════════════════════════════════

tab_static, tab_ai, tab_news = st.tabs([
    "📊 저장된 데이터", "🧠 AI 인텔리전스", "📰 뉴스"
])

# ─────────────────────────────────────────────────────────────
# TAB 1 : 저장된 정적 데이터
# ─────────────────────────────────────────────────────────────
with tab_static:
    sub1, sub2, sub3, sub4 = st.tabs([
        "자산배분", "국가별 익스포져", "Asset Class별 수익률", "다년도 수익률"
    ])

    with sub1:
        st.subheader("자산배분 비교 (% of Net Assets)")
        df_alloc = build_allocation_table(view_funds)
        if not df_alloc.empty:
            st.dataframe(df_alloc, use_container_width=True, height=420)
        else:
            st.info("좌측에서 기관을 선택하세요.")

        # 막대차트 – 단일 펀드 선택 시
        if len(view_funds) == 1:
            fund = view_funds[0]
            years = [y for (f,y) in STATIC_ALLOCATION if f==fund]
            if years:
                yr = st.selectbox("연도 선택", sorted(years,reverse=True), key="alloc_yr")
                alloc = STATIC_ALLOCATION.get((fund,yr),{})
                fig = px.bar(
                    pd.DataFrame({"자산군":list(alloc),"비중(%)":list(alloc.values())}).sort_values("비중(%)",ascending=True),
                    x="비중(%)", y="자산군", orientation="h",
                    title=f"{fund} ({yr}) 자산배분", text="비중(%)"
                )
                fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                st.plotly_chart(fig, use_container_width=True)

    with sub2:
        st.subheader("국가별 익스포져 (% of Portfolio)")
        df_geo = build_geo_table(view_funds)
        if not df_geo.empty:
            st.dataframe(df_geo, use_container_width=True, height=380)
        else:
            st.info("좌측에서 기관을 선택하세요.")

        # 레이더 차트
        common_regions = ["미국","유럽","아시아태평양","캐나다","중남미","호주","기타/EM"]
        if len(view_funds) >= 2:
            radar_rows=[]
            for (fund,year),geo in STATIC_GEO.items():
                if fund not in view_funds: continue
                for reg,pct in geo.items():
                    radar_rows.append({"기관":f"{fund}({year})","지역":reg,"비중":pct})
            if radar_rows:
                fig2=px.bar(pd.DataFrame(radar_rows),x="기관",y="비중",color="지역",
                            barmode="stack",title="국가별 익스포져 비교",range_y=[0,100])
                st.plotly_chart(fig2,use_container_width=True)

    with sub3:
        st.subheader("Asset Class별 1년 수익률 (%)")
        result_ret = build_returns_table(view_funds)
        if isinstance(result_ret, tuple):
            df_ret_fmt, df_ret_raw = result_ret
            if not df_ret_fmt.empty:
                ret_cols = [c for c in df_ret_fmt.columns]
                styled = df_ret_fmt.style.map(pct_color, subset=ret_cols)
                st.dataframe(styled, use_container_width=True, height=420)
        else:
            st.info("좌측에서 기관을 선택하세요.")

    with sub4:
        st.subheader("다년도 수익률 추이")
        df_myr = build_multiyear_table(view_funds)
        if not df_myr.empty:
            ret_cols2 = ["1년(%)","전년(%)","5년(연환,%)","10년(연환,%)","설정이후(%)"]
            available_cols = [c for c in ret_cols2 if c in df_myr.columns]
            styled2 = df_myr.style.map(pct_color, subset=available_cols)
            st.dataframe(styled2, use_container_width=True)

            # 시계열 선 차트
            chart_rows=[]
            for r in STATIC_MULTIYEAR:
                if r["fund"] not in view_funds: continue
                chart_rows.append({"기관":r["fund"],"연도":r["year"],"1년 수익률(%)":r["1년"]})
            if chart_rows:
                cdf=pd.DataFrame(chart_rows)
                fig3=px.line(cdf,x="연도",y="1년 수익률(%)",color="기관",
                             markers=True,title="기관별 1년 수익률 추이")
                st.plotly_chart(fig3,use_container_width=True)
        else:
            st.info("좌측에서 기관을 선택하세요.")

# ─────────────────────────────────────────────────────────────
# TAB 2 : AI 인텔리전스
# ─────────────────────────────────────────────────────────────
with tab_ai:
    # PDF 분석 실행
    if run_button:
        fund_timeseries={}
        report_summaries=""
        if uploaded_reports and client:
            st.info(f"{len(uploaded_reports)}개 PDF 분석 중...")
            bar=st.progress(0)
            for i,rpt in enumerate(uploaded_reports):
                with st.spinner(f"분석: {rpt.name}"):
                    summary,fund_name,year,allocation,prior_year,prior_alloc=summarize_pdf(rpt)
                    report_summaries+=summary+"\n\n"
                    if fund_name:
                        canon=normalize_fund_name(fund_name,list(fund_timeseries.keys()))
                        if canon not in fund_timeseries: fund_timeseries[canon]={}
                        if allocation: fund_timeseries[canon][year or "Unknown"]=allocation
                        if prior_alloc and prior_year and prior_year not in fund_timeseries[canon]:
                            fund_timeseries[canon][prior_year]=prior_alloc
                bar.progress((i+1)/len(uploaded_reports))
            bar.empty()
            st.session_state["fund_timeseries"]=fund_timeseries
            st.success(f"{len(uploaded_reports)}개 PDF 분석 완료")
        with st.spinner("뉴스 수집 중..."): articles=collect_news()
        result=None
        if client:
            with st.spinner("AI 분석 중..."): result=analyze_intelligence(articles,report_summaries)
        st.session_state.update({"result":result,"articles":articles})
    else:
        result          = st.session_state.get("result",None)
        articles        = st.session_state.get("articles",[])
        fund_timeseries = st.session_state.get("fund_timeseries",{})

    if not result and not fund_timeseries:
        st.info("PDF를 업로드하고 'Run Analysis'를 클릭하세요.")
    else:
        if result:
            st.header("📊 Executive Radar")
            cols=st.columns(5)
            for i,asset in enumerate(["Private Equity","Private Credit","Infrastructure","Real Estate","Secondaries"]):
                cols[i].metric(asset,result.get("signals",{}).get(asset,"-"))
            st.header("🧠 AI Brief"); st.info(result.get("brief",""))
            st.header("🎯 기회 요인")
            for item in result.get("opportunities",[]): st.success(item)
            st.header("🚨 리스크")
            alerts=result.get("risk_alerts",[])
            [st.warning(a) for a in alerts] if alerts else st.success("특이 리스크 없음")
            st.header("🏢 국내 보험사 시사점"); st.write(result.get("implications",""))

        # PDF 분석 결과 배분 차트
        if fund_timeseries:
            st.header("🏦 업로드 PDF 배분 차트")
            fund_names=list(fund_timeseries.keys())
            sel=st.selectbox("펀드",fund_names,key="pdf_fund")
            yrs=sorted(fund_timeseries[sel].keys(),reverse=True)
            yr=st.selectbox("연도",yrs,key="pdf_yr")
            alloc=fund_timeseries[sel][yr]
            df_b=pd.DataFrame({"Asset":list(alloc),"Weight":[round(float(v),1) for v in alloc.values()]}).sort_values("Weight",ascending=True)
            total=df_b["Weight"].sum()
            fig=px.bar(df_b,x="Weight",y="Asset",orientation="h",
                       title=f"{sel} ({yr}){' (합계 '+str(round(total,1))+'%)' if not 90<=total<=110 else ''}",
                       text="Weight")
            fig.update_traces(texttemplate="%{text:.1f}%",textposition="outside")
            st.plotly_chart(fig,use_container_width=True)

            if len(fund_timeseries[sel])>=2:
                st.subheader("시계열 변화")
                rows2=[]
                for y2,ad in sorted(fund_timeseries[sel].items()):
                    tot=sum(float(v) for v in ad.values())
                    for asset,w in ad.items():
                        rows2.append({"Year":str(y2),"Asset":asset,"Weight":round(float(w)/tot*100,1) if tot else float(w)})
                fig2=px.bar(pd.DataFrame(rows2),x="Year",y="Weight",color="Asset",
                            barmode="stack",title=f"{sel} 배분 변화",range_y=[0,100])
                st.plotly_chart(fig2,use_container_width=True)

# ─────────────────────────────────────────────────────────────
# TAB 3 : 뉴스
# ─────────────────────────────────────────────────────────────
with tab_news:
    articles=st.session_state.get("articles",[])
    if articles:
        for row in articles[:30]:
            with st.expander(row["title"]):
                st.write(row["description"])
                if row["link"]: st.markdown(f"[원문 보기]({row['link']})")
    else:
        st.info("'Run Analysis'를 실행하면 최신 뉴스가 표시됩니다.")
