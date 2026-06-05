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
    "Private Equity": (
        "글로벌 주요 기관들은 바이아웃 중심에서 성장형(Growth)·Venture Growth로 전략을 다변화하고 있으며, "
        "AI·테크·헬스케어 섹터 집중도가 높아지고 있음. "
        "2022～2023년 밸류에이션 조정과 엑시트 시장 위축으로 대부분 기관이 비중을 축소했으나, "
        "2024～2025년 점진적 회복 국면에서 선별적 확대가 재개됨. "
        "빈티지 분산 전략과 GP 재선별(Manager Selection)이 성과의 핵심 결정 요인."
    ),
    "Private Credit": (
        "2022년 이후 금리 급등과 은행권 대출 규제 강화가 맞물리며 직접대출(Direct Lending) 시장이 급성장. "
        "변동금리 구조로 금리 고점 환경에서 스프레드 수혜를 직접 누렸으며, "
        "주요 기관의 비중이 7～14% 수준으로 확대됨. "
        "단, NAV 파이낸싱·합성 리스크 이전 등 구조적 복잡성이 증가하고 있어 "
        "신용 분석 역량과 LTV 관리가 중요해지고 있음. 금리 인하 국면에서의 스프레드 압축 여부 주목."
    ),
    "Infrastructure": (
        "에너지 전환(재생에너지·송배전)과 디지털 인프라(데이터센터·광케이블)가 신규 투자의 핵심 타깃. "
        "CPPIB 지속가능에너지 +23.2%, NPS 인프라 +23.0% 등 고수익 자산군으로 부상. "
        "글로벌 인프라 자산 가격 상승으로 일부 기관이 차익 실현에 나섰으며(OTPP 17%→13%, PSP 13%→10.7%), "
        "신규 진입 시 밸류에이션 부담이 증가하는 추세. "
        "정책 변화(미국 IRA, EU 그린딜)가 투자 기회와 리스크를 동시에 제공 중."
    ),
    "Real Estate": (
        "글로벌 오피스 시장의 구조적 침체(재택근무 정착)로 CalPERS·PSP·CPPIB 등 대부분 기관이 "
        "비중을 대폭 축소함. 평가손 인식은 2024～2025년을 기점으로 마무리 단계에 접어들었으나, "
        "공실률 회복까지 추가 시간 필요. 물류(E-commerce 수요), 주거용(임대주택 부족), "
        "데이터센터(AI 수요) 부동산으로의 포트폴리오 재편이 가속화 중. "
        "아시아 물류·주거형 부동산에 대한 기관 관심도가 점진적으로 증가."
    ),
    "Hedge Fund/Other": (
        "CalPERS(10.5%→3.4%)·OTPP 등 주요 기관이 고비용·저투명성을 이유로 헤지펀드 비중을 대폭 축소. "
        "CTA·매크로 전략은 2022년 급등 이후 2023～2024년 성과 부진으로 매력이 감소함. "
        "반면 재보험(ILS) 전략은 자연재해 빈도 증가로 스프레드가 역대 최고 수준을 유지하며 재조명. "
        "PSP의 천연자원·원자재 투자는 에너지 전환 수혜 자산으로 재평가 받고 있음. "
        "절대수익 전략 유지 기관들은 CTA 대신 Reinsurance ILS 비중 확대 검토 중."
    ),
}

RECENT_ISSUES = {
    "국민연금(NPS)": (
        "2024년 수익률 15.0%로 2년 연속 사상 최고치 달성. 해외주식(+34.6%)이 성과를 주도했으며, "
        "인프라(+23.0%)·사모주식(+21.2%)의 대체투자도 두 자릿수 수익을 기록. "
        "대체투자 비중이 17.1%(206.9조 원)에 도달해 장기 목표치를 처음 충족. "
        "반면 국내주식은 -7.0%로 부진했으며, 해외부동산 오피스 자산의 리스크 모니터링이 지속 중. "
        "향후 PE·인프라 위탁운용사 추가 선정과 채권 비중 추가 축소가 주요 과제."
    ),
    "CPPIB": (
        "FY2026(2025년 3월말) 순수익률 7.8%. 지속가능에너지(Sust. Energy Infra) +23.2%로 신규 카테고리 성과 우수. "
        "반면 Active Equities 전략에서 -$3.5B 손실이 발생해 전략 재검토 중. "
        "PE 비중을 29%→22%로 대폭 축소하고 공모주식(36%)을 확대하는 구조 전환을 단행. "
        "부동산·인프라·에너지를 'Real Assets'로 통합하는 분류 체계 개편도 완료. "
        "FY2026 누적 운용자산 C$793B으로 역대 최대 달성."
    ),
    "CalPERS": (
        "FY2025(2025년 6월말) 수익률 11.6%로 벤치마크 대비 +1.7%p 초과 달성. "
        "PE가 15.7%로 5년 누적 최고치를 기록하며 목표 비중(17%) 달성에 근접. "
        "Private Debt 신설 카테고리가 성장하며 3.4%에 도달. "
        "부동산은 오피스 손실 반영 이후 7.4%로 안정화 단계에 진입. "
        "펀딩비율 79%로 개선 추세이며 이사회에서 PE 목표 비중 추가 상향 논의 진행 중."
    ),
    "OTPP": (
        "2025년 수익률 6.7%로 벤치마크 대비 -5.0%p 하회. PE 포트폴리오의 -5.3% 손실이 주요 원인. "
        "반면 신설 카테고리인 Venture Growth가 +30.2%의 탁월한 성과를 기록하며 장기 성장 동력을 확인. "
        "인프라를 17%→13%로 축소하며 차익을 실현했고, 공모주식은 14%→18%로 확대. "
        "채권은 금리 정상화에 맞춰 39%→23%로 대폭 축소하는 대규모 리밸런싱을 단행. "
        "PE 전략 재검토 및 Venture Growth 확대 여부가 2026년 핵심 관전 포인트."
    ),
    "PSP Investments": (
        "FY2025(2025년 3월말) 수익률 12.6%로 분석 대상 기관 중 최고 성과 달성. 5년 누적 10.6%. "
        "오피스 중심의 부동산 손실 인식이 FY2024~FY2025를 거쳐 마무리 단계에 접어들었으며, "
        "부동산 비중은 10.3%→8.9%로 추가 감소했으나 감소 폭은 완화. "
        "공모주식(자본시장) 비중을 21%→26.6%로 확대해 역대 최고치를 기록하며 안정적 성장 기반 구축. "
        "Private Credit(10.1%)·인프라 직접투자를 핵심 역량으로 유지하며 균형 잡힌 포트폴리오 달성."
    ),
}

# 기관별 리밸런싱 배경 해설 (5개년)
REBAL_NARRATIVE = {
    "국민연금(NPS)": {
        "context": "국민연금은 2021～2024년 동안 장기 목표인 대체투자 17% 달성을 위해 체계적 확대 전략을 이행했습니다. 저금리 환경과 공모시장 변동성 확대에 대응해 사모(PE)·인프라 비중을 꾸준히 늘린 반면, 채권 비중은 금리 상승 리스크를 반영해 단계적으로 축소했습니다.",
        "issue": "2022년 글로벌 주식·채권 동반 하락으로 -8.2% 손실을 기록했으나, 이후 대체자산의 방어적 역할이 부각되며 대체투자 확대 기조를 강화했습니다. 공모주식은 해외 비중(특히 북미·선진국)을 늘려 2023～2024년 높은 성과를 거뒀습니다.",
        "outlook": "2025년 이후 인프라와 사모대출 중심의 추가 확대가 예상되며, 국내 부동산은 상업용 오피스 약세로 비중 유지 또는 축소될 전망입니다.",
    },
    "CPPIB": {
        "context": "CPPIB는 FY2022~FY2026 동안 액티브 알파 전략의 일환으로 사모주식(PE) 비중을 32%→22%로 큰 폭 축소했습니다. 이는 2022～2023년 PE 밸류에이션 조정과 엑시트 시장 위축에 대응한 것으로, 동시에 공모주식을 27%→36%로 확대해 유동성을 확보했습니다.",
        "issue": "인프라·부동산을 FY2026부터 'Real Assets'로 통합 공시하는 구조 개편이 이루어졌으며, 지속가능에너지 인프라를 별도 카테고리로 신설했습니다. Active Equities 전략에서 FY2026에 -$3.5B 손실이 발생해 공모주식 내 전략 재검토 중입니다.",
        "outlook": "PE 비중 축소가 일단락되고 Private Credit은 금리 고점 수혜로 유지될 전망입니다. 지속가능에너지 인프라는 중장기 확대 기조를 유지할 것으로 보입니다.",
    },
    "CalPERS": {
        "context": "CalPERS는 FY2021~FY2025 동안 사모주식(PE)을 7.9%→15.7%로 두 배 이상 확대했습니다. 이는 Board가 승인한 PE 목표 비중 상향(13%→17%)의 이행 과정이며, 공모주식 중심의 포트폴리오에서 탈피해 초과수익 창출을 목표로 합니다.",
        "issue": "부동산 비중이 11.9%→7.4%로 감소했는데, 이는 오피스·소매 부동산 평가손 반영과 포트폴리오 구조조정의 결과입니다. 헤지펀드/기타 비중도 10.5%→3.4%로 대폭 축소되어 복잡성을 줄이고 비용을 절감하는 방향으로 이동했습니다.",
        "outlook": "펀딩비율 79% 개선 추세가 지속되면 PE 추가 확대 여력이 생기며, Private Debt 신설 카테고리가 본격화될 전망입니다.",
    },
    "OTPP": {
        "context": "OTPP는 2021～2025년 인프라를 11%→13%로 유지하다 고점(17%) 이후 축소했고, 대신 공모주식을 11%→18%로 확대했습니다. 2022～2023년 글로벌 인프라 자산 가격 상승으로 차익을 실현하고, 유동성 높은 공모 자산을 늘려 리밸런싱 여력을 확보했습니다.",
        "issue": "PE 비중은 2025년 25%로 소폭 축소됐는데, Venture Growth 카테고리를 신설해 성장형 자산 내 세분화를 도모했습니다. 2025년 벤치마크 대비 -5.0%p 언더퍼폼은 PE 포트폴리오(-5.3%)의 부진이 주된 원인입니다.",
        "outlook": "Venture Growth(+30.2%, 2025) 성과를 바탕으로 PE 내 성장형 비중 확대가 이루어질 것으로 예상됩니다.",
    },
    "PSP Investments": {
        "context": "PSP는 FY2021~FY2025 동안 부동산을 13.1%→8.9%로 축소했습니다. 이는 글로벌 오피스 시장 침체와 직접 연관되며, 북미·유럽 오피스 자산의 평가손을 FY2024~FY2025에 걸쳐 본격 반영한 결과입니다. 동시에 공모주식(Capital Markets)을 21%→26.6%로 확대해 하방 리스크를 보완했습니다.",
        "issue": "Private Credit이 7.1%→10.1%로 증가한 것은 금리 고점 환경에서 대출형 자산의 매력이 높아졌기 때문입니다. 인프라 역시 9%→10.7%로 소폭 늘어났으나, FY2025에는 오히려 13%→10.7%로 축소되며 포트폴리오 재조정이 이루어졌습니다.",
        "outlook": "오피스 부동산 손실 인식이 마무리 단계에 접어들면서 부동산 비중 추가 감소폭은 제한될 전망이며, 물류·주거형 부동산으로의 전환이 예상됩니다.",
    },
}

# 연도별 리밸런싱 해설 (key: (from_year, to_year) - norm_year 기준)
REBAL_YEARLY = {
    "국민연금(NPS)": {
        ("2020","2021"): {
            "title": "저금리 환경 대응 — 대체투자 확대 원년",
            "text": "저금리 장기화로 채권 수익률이 하락하면서 수익률 제고를 위한 대체투자 확대가 본격 시작됐습니다. 사모주식(PE)을 4.0%→5.0%로 늘리고 인프라도 소폭 증가했습니다. 글로벌 주식 강세(수익률 10.8%)로 공모주식도 우호적이었으며, 채권은 비중을 서서히 줄이기 시작했습니다.",
        },
        ("2021","2022"): {
            "title": "2022 위기 — 주식·채권 동반 하락, -8.2% 손실",
            "text": "연준 긴축 전환으로 금리가 급등하며 채권과 주식이 동시에 하락하는 유례없는 손실 연도였습니다(수익률 -8.2%). 채권 비중이 43.0%→42.3%로 일부 감소했으나 여전히 높은 채권 비중이 손실을 키웠습니다. 이 경험을 계기로 채권 축소·대체투자 확대 기조가 더욱 강화됐으며, 사모대출(PC)이 이 해부터 독립 항목으로 분리 공시됐습니다.",
        },
        ("2022","2023"): {
            "title": "시장 회복 — 해외주식 주도, 대체투자 순항",
            "text": "글로벌 증시 반등으로 공모주식이 41.1%→45.2%로 급증하며 수익률 13.6% 회복을 이끌었습니다. PE와 인프라는 목표 비중을 향해 꾸준히 확대됐으며, 부동산은 글로벌 오피스 하락에도 국내 부동산 안정으로 소폭 감소에 그쳤습니다. 채권은 38.8%로 계속 축소됐습니다.",
        },
        ("2023","2024"): {
            "title": "사상 최고 수익률 15.0% — 대체투자 목표 17% 달성",
            "text": "해외주식 +34.6%(엔비디아 등 AI 관련주 강세)에 힘입어 전체 수익률 15.0%라는 사상 최고 기록을 달성했습니다. 대체투자 합계가 17.1%에 도달해 장기 목표치에 처음 근접했으며, PE(+21.2%)·인프라(+23.0%)도 고수익을 기록했습니다. 채권 비중은 36.0%까지 낮아져 포트폴리오의 성장지향성이 강화됐습니다.",
        },
    },
    "CPPIB": {
        ("2022","2023"): {
            "title": "PE 최고점 이후 조정 시작 — 수익률 1.3% 부진",
            "text": "PE가 32%→33%로 소폭 증가했으나 이후 축소 전환점이 됐습니다. 글로벌 PE 밸류에이션 재조정과 엑시트 시장 위축이 시작된 해로, 수익률 1.3%로 크게 저조했습니다. 인플레 대응을 위해 실물자산(인프라·부동산) 비중을 유지했으며, 채권을 7%→12%로 확대해 금리 수혜를 추구했습니다.",
        },
        ("2023","2024"): {
            "title": "PE 본격 축소 — 공모주식 확대로 유동성 확보",
            "text": "PE를 33%→31%로 축소하며 구조적 리밸런싱이 가속됐습니다. Private Credit을 13%→13%로 유지하며 고금리 대출 수익을 추구했고, 공모주식을 24%→28%로 확대해 유동성을 높였습니다. 수익률 8.0%로 회복세를 보였으나 PE 포트폴리오의 미실현 손실이 지속됐습니다.",
        },
        ("2024","2025"): {
            "title": "PE 추가 감소 — 채권 확대로 금리 고점 수혜",
            "text": "PE가 31%→29%로 추가 감소했으며, 채권을 12%→15%로 크게 늘려 고금리 환경에서 확정금리 수익을 확보했습니다. Private Credit은 13%→11%로 소폭 축소됐으며, 인프라는 8%→9%로 안정적으로 유지됐습니다. 수익률 9.3%.",
        },
        ("2025","2026"): {
            "title": "대규모 구조 개편 — Real Assets 통합, PE 22%로 급감",
            "text": "5년간 가장 큰 구조적 변화가 일어난 해입니다. PE가 29%→22%로 -7%p 급감했으며, 부동산·인프라·에너지를 'Real Assets'로 통합한 새로운 분류 체계가 도입됐습니다. 공모주식을 29%→36%로 확대해 유동성을 대폭 높였으나, Active Equities 전략에서 -$3.5B 손실이 발생해 전체 수익률은 7.8%에 그쳤습니다.",
        },
    },
    "CalPERS": {
        ("2021","2022"): {
            "title": "PE 확대 원년 — 2022년 -6.1% 손실로 전략 재검토",
            "text": "PE를 7.9%→11.0%로 대폭 확대하는 전략적 전환을 시작했습니다. 그러나 같은 해 금리 급등·주식 하락으로 -6.1% 손실을 기록하며 포트폴리오 전체를 재검토하게 됩니다. 헤지펀드/기타 비중(7→10.5%)은 이후 지속적으로 축소되는 전환점이 됩니다.",
        },
        ("2022","2023"): {
            "title": "헤지펀드 대폭 축소 — 단순화·비용절감 전략 본격화",
            "text": "헤지펀드/기타를 10.5%→5.5%로 절반 가까이 줄이는 대규모 단순화 작업이 진행됐습니다. 이는 복잡한 전략의 비용 대비 효율성에 대한 이사회의 재평가 결과입니다. PE는 11.9%로 확대를 지속했으며, 부동산도 11%대를 유지했습니다. 수익률 5.8%로 회복.",
        },
        ("2023","2024"): {
            "title": "부동산 급락 — 오피스 손실 본격 반영",
            "text": "부동산이 11.2%→8.5%로 -2.7%p 급감했습니다. 이는 샌프란시스코·LA 등 캘리포니아 주요 도시 오피스 시장 침체가 직접 반영된 것으로, 상당 규모의 평가손이 인식됐습니다. PE는 14.1%로 꾸준히 확대됐으며, 수익률 9.3%로 양호했습니다.",
        },
        ("2024","2025"): {
            "title": "PE 15.7%로 역대 최고 — Private Credit 신규 성장",
            "text": "PE가 15.7%로 5년간 최고치를 기록하며 목표 17% 달성에 근접했습니다. Private Credit이 독립 카테고리로 성장해 3.4%에 달했으며, 고금리 대출 수익이 긍정적으로 기여했습니다. 부동산은 7.4%로 추가 감소했으나 감소 폭은 완화됐습니다. 수익률 11.6%, 벤치마크 +1.7%p 초과.",
        },
    },
    "OTPP": {
        ("2021","2022"): {
            "title": "채권 급확대 — 실질금리 채권으로 인플레 헤지",
            "text": "채권을 19%→35%로 대폭 확대한 것이 가장 큰 특징입니다. 금리 급등 환경에서 OTPP는 인플레이션 연동 채권(실질금리 상품)을 적극 활용해 손실을 방어했습니다. 인프라도 11%→16%로 확대해 실물자산 헤지를 강화했습니다. 이 해 수익률 4.0%는 글로벌 시장 대비 선방한 결과입니다.",
        },
        ("2022","2023"): {
            "title": "포트폴리오 안정화 — 고금리 환경 적응",
            "text": "전년의 방어적 포지션을 유지하며 안정 국면을 지속했습니다. PE·인프라·부동산 등 대체투자 비중을 거의 일정하게 유지했으며, Private Credit은 14%→16%로 소폭 확대해 고금리 대출 수익을 추구했습니다. 다만 수익률 1.9%로 부진했으며, 글로벌 PE 밸류에이션 조정의 영향을 받았습니다.",
        },
        ("2023","2024"): {
            "title": "채권 대폭 축소 — 금리 정상화에 맞춰 리밸런싱",
            "text": "금리 고점 인식 후 채권을 39%→30%로 -9%p 대폭 축소했습니다. 공모주식을 10%→14%로 확대해 성장 자산으로 자금을 이동시켰습니다. Private Credit은 16%→14%로 소폭 축소됐으며, 수익률 9.4%로 회복됐습니다.",
        },
        ("2024","2025"): {
            "title": "Venture Growth 신설 — 인프라 차익 실현",
            "text": "글로벌 인프라 자산 가격 고점에서 차익을 실현해 인프라를 17%→13%로 축소했습니다. 공모주식이 14%→18%로 확대됐으며, PE에서 Venture Growth 카테고리를 분리·신설해 성장형 자산을 별도 관리하기 시작했습니다. 수익률 6.7%로 벤치마크 대비 -5.0%p 언더퍼폼했으며, PE 포트폴리오 -5.3%가 주요 원인이었습니다.",
        },
    },
    "PSP Investments": {
        ("2021","2022"): {
            "title": "Private Credit 확대 — 고금리 전환에 선제 대응",
            "text": "금리 상승 전환 초기에 Private Credit을 7.1%→9.5%로 확대해 변동금리 대출 수익을 선제적으로 확보했습니다. 부동산은 13.1%→13.5%를 유지했으나 이후 하락의 전환점이 됐습니다. 인프라도 9%→10.2%로 소폭 증가했으며 수익률 10.9%로 양호했습니다.",
        },
        ("2022","2023"): {
            "title": "인프라 확대 — 실물자산 헤지 강화",
            "text": "인프라를 10.2%→12.1%로 확대해 인플레이션 헤지와 안정적 현금흐름을 강화했습니다. Private Credit도 9.5%→10.7%로 지속 성장했습니다. 부동산은 13.1%로 고점을 유지했으나 글로벌 오피스 시장 우려가 커지기 시작했습니다. 수익률 4.4%로 다소 낮았습니다.",
        },
        ("2023","2024"): {
            "title": "오피스 손실 직격 — 부동산 13.1%→10.3% 급감",
            "text": "글로벌 오피스 시장 침체가 직접 반영되며 부동산이 13.1%→10.3%로 -2.8%p 급감했습니다. 북미·유럽 오피스 자산의 대규모 평가손이 인식됐으며, 이는 FY2025까지 지속됩니다. 인프라는 12.1%→13.0%로 최고치를 기록했으며 수익률 7.2%였습니다.",
        },
        ("2024","2025"): {
            "title": "손실 마무리 + 자본시장 최고치 — 수익률 12.6%",
            "text": "오피스 손실 인식이 마무리 단계에 접어들며 부동산이 10.3%→8.9%로 추가 감소했으나 속도는 완화됐습니다. 공모주식(자본시장)을 21%→26.6%로 크게 확대해 5년간 최고 비중을 기록했으며, 포트폴리오 안정화와 시장 상승이 맞물려 수익률 12.6%라는 최고 성과를 달성했습니다. 인프라는 13%→10.7%로 축소되며 차익 실현이 진행됐습니다.",
        },
    },
}


# ── 자산군 개요 / 투자매력 / 리스크 / 최근 이슈 ─────────────────
ASSET_OVERVIEW = {
    "Private Equity": {
        "overview":   "비상장 기업 지분 투자를 통해 장기 자본이득을 추구하는 자산군. 바이아웃·성장형·벤처 등 전략별로 위험-수익 프로파일이 상이하며, GP 역량과 빈티지 분산이 핵심 성과 결정 요인임.",
        "attraction": "장기적 초과수익(알파) 창출 가능 / 경영 참여를 통한 가치 제고 / 공모시장 대비 투자 유니버스 확장 / 인플레이션 환경에서도 실적 연동 수익 확보 가능",
        "risk":       "장기 비유동성(Lock-up 7～10년) / 경기 침체기 밸류에이션 조정 및 엑시트 지연 / GP 선정 역량에 따른 성과 편차 큼 / 고금리 환경에서 레버리지 바이아웃 수익성 압박",
        "recent":     "2022～2023년 금리 상승으로 밸류에이션 조정 및 엑시트 시장 위축. 2024년 이후 선택적 회복세. 주요 기관들은 바이아웃 비중 축소 후 성장형·Venture Growth로 전환 중.",
    },
    "Private Credit": {
        "overview":   "비상장 기업 대상 직접대출(Direct Lending)·메자닌·디스트레스드 투자 등을 포함하는 사모 대출 자산군. 2022년 이후 은행 규제 강화로 시장 급성장.",
        "attraction": "고금리 환경에서 변동금리 구조로 직접 수혜 / 은행 대비 신속한 대출 실행 / PE 대비 하방 보호(담보·우선순위) / 꾸준한 현금흐름 창출",
        "risk":       "차주 신용위험 집중 / NAV 파이낸싱 등 구조적 리스크 증가 / 경기 침체 시 부실 채권 급증 가능 / 유동성 프리미엄 희석 우려",
        "recent":     "글로벌 주요 기관들 비중 확대 지속. OTPP·PSP 14～10% 수준 유지. 금리 고점 이후에도 스프레드 매력 유지. NAV 파이낸싱 리스크에 대한 모니터링 강화 필요.",
    },
    "Infrastructure": {
        "overview":   "도로·공항·에너지·데이터센터 등 필수 인프라 자산에 대한 지분/채권 투자. 장기 계약 기반 안정적 현금흐름과 인플레이션 연동 특성이 핵심 매력.",
        "attraction": "인플레이션 헤지 기능 / 장기 안정적 현금흐름 / 규제·독점적 지위 보호 / 에너지 전환 수요로 재생에너지·디지털 인프라 투자 급성장",
        "risk":       "규제 리스크 및 정치적 위험 / 초기 개발 단계 프로젝트 비용 초과 / 금리 상승 시 할인율 상승으로 가치 하락 / 글로벌 인프라 가격 고평가 우려",
        "recent":     "재생에너지(태양광·풍력)·데이터센터 신규 투자 집중. CPPIB 지속가능에너지 +23.2%. PSP 인프라 차익 실현(13%→10.7%). 디지털 인프라 밸류에이션 급등 주의.",
    },
    "Real Estate": {
        "overview":   "상업용·물류·주거·특수목적 부동산 자산에 대한 직접투자 또는 REIT·펀드를 통한 간접투자. 임대수익과 자본이득 두 가지 수익원을 가짐.",
        "attraction": "인플레이션 헤지 기능 / 임대수익을 통한 안정적 현금흐름 / 자산 담보 리스크 관리 / 물류·데이터센터 등 신산업 부동산 고성장",
        "risk":       "오피스 시장 구조적 침체(재택근무 정착) / 금리 상승 시 자산가치 하락 및 조달비용 증가 / 상업용 부동산 부실 대출 연쇄 우려 / 지역별 수급 불균형",
        "recent":     "글로벌 오피스 손실이 CalPERS·PSP·CPPIB 등에 반영 완료 단계. 물류·주거형 선호 지속. 국민연금 국내 부동산 비중 축소 방향. 데이터센터 부동산 별도 카테고리화 진행 중.",
    },
    "Hedge Fund/Other": {
        "overview":   "절대수익 추구 전략(Long/Short·매크로·CTA·Event-driven 등)과 천연자원·원자재·재보험(ILS) 등 특수목적 자산을 포함하는 기타 대체투자 카테고리.",
        "attraction": "시장 방향성 중립 포지션 / 포트폴리오 분산 효과 / 고금리 환경에서 매크로·CTA 전략 수혜 / 재보험(ILS) 고스프레드 유지",
        "risk":       "높은 운용 보수(2and20 구조) / 전략 투명성 제한 / 시장 위기 시 유동성 리스크 / 성과의 GP 역량 의존도 높음",
        "recent":     "CalPERS·OTPP 헤지펀드 비중 대폭 축소(비용 절감 목적). CTA·매크로 전략 2024년 부진. 재보험 ILS는 자연재해 수요로 높은 스프레드 유지. PSP 천연자원 관심 증가.",
    },
}

# ── 기관별 특징 요약 ──────────────────────────────────────────
FUND_CHARACTERISTIC = {
    "국민연금(NPS)": (
        "세계 3위 규모 공적연금(AUM 약 $880B). 2040년대 기금 소진 우려에 대응해 "
        "대체투자 17% 목표를 달성했으며, 해외 PE·인프라·사모대출 위탁운용사 추가 선정을 지속 추진 중. "
        "2024년 해외주식(+34.6%)과 인프라(+23.0%)·PE(+21.2%)의 고수익으로 수익률 15.0% 달성. "
        "채권 비중을 단계적으로 축소하며 성장지향형 포트폴리오로 전환하고 있으나, "
        "국내주식(-7.0%) 부진과 해외부동산 오피스 리스크는 지속 모니터링 필요."
    ),
    "CPPIB": (
        "캐나다 최대 연기금(AUM C$793B)으로 글로벌 최상위 직접투자·공동투자(Co-investment) 역량 보유. "
        "FY2022 PE 32%에서 FY2026 22%로 구조적 축소를 단행하며 공모주식(36%)으로 전환, "
        "유동성 확보와 포트폴리오 단순화에 집중. 지속가능에너지 인프라(+23.2%) 신설 카테고리가 성장 동력. "
        "Active Equities 전략에서 FY2026 -$3.5B 손실이 발생해 전략 재검토 중이며, "
        "PE 하단 수렴 여부와 Real Assets 통합 개편 이후 성과가 핵심 관전 포인트."
    ),
    "CalPERS": (
        "미국 최대 주 공무원연금(AUM $635B)으로 캘리포니아 주정부 직원 약 200만 명 대상. "
        "이사회 승인으로 PE 목표 비중을 17%로 상향하고 5년간 7.9%→15.7%로 두 배 확대 이행 중. "
        "헤지펀드/기타를 10.5%→3.4%로 대폭 축소하며 포트폴리오를 단순화했고, "
        "부동산 오피스 손실(11.9%→7.4%)은 마무리 단계. 펀딩비율 79%로 개선 추세이며, "
        "Private Debt 신설 카테고리 성장과 PE 목표 비중 추가 상향 논의가 진행 중."
    ),
    "OTPP": (
        "캐나다 온타리오주 교원연금(AUM C$279B)으로 13년 연속 완전적립 달성. "
        "직접투자 비율이 높으며 Venture Growth 카테고리를 신설해 성장형 자산을 별도 관리. "
        "2022년 금리 급등기에 채권을 19%→35%로 대폭 확대해 시장 대비 선방했으나, "
        "2025년 PE 포트폴리오(-5.3%)가 발목을 잡아 벤치마크 대비 -5.0%p 언더퍼폼. "
        "인프라 차익 실현(17%→13%) 후 공모주식(18%)을 확대하며 포트폴리오를 성장 방향으로 재편 중."
    ),
    "PSP Investments": (
        "캐나다 연방 공무원·군인·RCMP 연금(AUM C$300B)으로 Private Credit·인프라 직접투자에 강점. "
        "글로벌 오피스 시장 침체로 부동산 비중이 13.1%→8.9%로 급감했으나 손실 인식은 마무리 단계. "
        "공모주식(자본시장)을 21%→26.6%로 역대 최고 수준으로 확대하며 안정성을 강화했고, "
        "FY2025 수익률 12.6%로 분석 대상 기관 중 최고 성과 달성. "
        "Private Credit(10.1%)과 인프라 직접투자를 핵심 역량으로 유지하며 장기 성장 기반 구축 중."
    ),
}

# ── 기관별 최근 시그널 ────────────────────────────────────────
INST_SIGNAL = {
    "국민연금(NPS)":   "🟡 Watch — 대체투자 17% 목표 달성 후 세부 자산군 내 질적 고도화 필요. 해외부동산 오피스 회수 점검 및 PE·인프라 위탁운용사 추가 선정 진행 중. 국내주식 -7.0% 부진 대응 전략 검토.",
    "CPPIB":           "🟡 Watch — FY2026 Active Equities -$3.5B 손실 재발 방지 대책 수립 필요. PE 22% 하단 수렴 여부와 Real Assets 통합 개편 후 성과 검증이 핵심 모니터링 포인트.",
    "CalPERS":         "🟢 Stable — PE 목표 비중 17% 향한 순조로운 확대 이행 중. FY2025 수익률 11.6%로 벤치마크 +1.7%p 초과. Private Debt 신설 카테고리 성장 모멘텀 지속.",
    "OTPP":            "🔴 Alert — 2025년 PE 포트폴리오 -5.3% 언더퍼폼으로 벤치마크 -5.0%p 하회. Venture Growth +30.2% 선전에도 전체 성과 부진. PE 전략 재검토 및 GP 재선별 필요.",
    "PSP Investments": "🟢 Stable — FY2025 수익률 12.6%로 분석 대상 중 최고 성과. 5년 누적 수익률 10.6%. 오피스 손실 인식 완료, 자본시장(48.7%) 역대 최고. 안정적 성장 궤도 진입.",
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

# ── 뉴스 관련성 필터 ──────────────────────────────────────────
PENSION_MUST_KW = [
    "연기금","pension fund","pension investment","asset allocation","투자","대체투자",
    "운용","포트폴리오","private equity","infrastructure","real estate","private credit",
    "direct lending","사모","인프라","부동산","수익률","allocation","alternative",
    "endowment","sovereign fund","institutional investor","약정","위탁운용",
]
PENSION_EXCLUDE_KW = [
    "노령연금","기초연금","수급자","수령방법","신청방법","납부","연금보험료",
    "개인연금","연금저축","세금","소득공제","퇴직금","실업급여","건강보험",
]

# ── 해외 공개 RSS 피드 ────────────────────────────────────────
GLOBAL_RSS_FEEDS = [
    ("Pensions & Investments", "https://www.pionline.com/rss/home"),
    ("Reuters Business",        "https://feeds.reuters.com/reuters/businessNews"),
    ("IPE (Inst. Investor EU)", "https://www.ipe.com/rss"),
]

@st.cache_data(ttl=3600)
def fetch_global_rss(extra_kw=None):
    import xml.etree.ElementTree as ET
    search_kw = [
        "pension","endowment","sovereign","alternative","private equity",
        "infrastructure","real estate","private credit","asset allocation",
        "institutional investor","fund manager","portfolio",
    ]
    if extra_kw:
        search_kw += [k.lower() for k in extra_kw]
    articles, seen = [], set()
    for source, url in GLOBAL_RSS_FEEDS:
        try:
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent":"Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            root  = ET.fromstring(resp.content)
            items = root.findall('.//item')
            count = 0
            for item in items:
                title = (item.findtext('title') or "").strip()
                desc  = (item.findtext('description') or "").strip()
                link  = (item.findtext('link') or "").strip()
                text  = (title + " " + desc).lower()
                if not any(k in text for k in search_kw):
                    continue
                if link not in seen:
                    seen.add(link)
                    articles.append({
                        "title":       title[:150],
                        "description": clean_html(desc[:400]),
                        "link":        link,
                        "pubDate":     item.findtext('pubDate', ''),
                        "source":      source,
                        "is_global":   True,
                    })
                    count += 1
                    if count >= 6:
                        break
        except Exception:
            pass
    return articles

@st.cache_data(ttl=3600)
def fetch_news(keywords):
    articles, seen = [], set()

    # ── 네이버 API (한국 뉴스) ─────────────────────────────
    if NAVER_CLIENT_ID:
        expanded = []
        for kw in keywords:
            expanded.append(kw)
            if not any(x in kw for x in ["투자", "운용", "펀드"]):
                expanded.append(kw + " 투자")
        for kw in expanded[:8]:
            try:
                r = requests.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    headers={"X-Naver-Client-Id":     NAVER_CLIENT_ID,
                             "X-Naver-Client-Secret": NAVER_CLIENT_SECRET},
                    params={"query": kw, "display": 15, "sort": "date"},
                    timeout=15)
                for item in r.json().get("items", []):
                    lnk   = item.get("originallink", "")
                    title = clean_html(item.get("title", ""))
                    desc  = clean_html(item.get("description", ""))
                    text  = (title + " " + desc).lower()
                    if any(ex in text for ex in PENSION_EXCLUDE_KW):
                        continue
                    if not any(m in text for m in PENSION_MUST_KW):
                        continue
                    if lnk not in seen:
                        seen.add(lnk)
                        articles.append({
                            "title":       title,
                            "description": desc,
                            "link":        lnk,
                            "pubDate":     item.get("pubDate", ""),
                            "source":      "Naver",
                            "is_global":   False,
                        })
            except Exception:
                pass

    # ── 해외 RSS (English) ─────────────────────────────────
    try:
        global_arts = fetch_global_rss(extra_kw=keywords)
        for a in global_arts:
            if a["link"] not in seen:
                seen.add(a["link"])
                articles.append(a)
    except Exception:
        pass

    return articles

def score_news_relevance(title, desc, fund_kws, asset_kws=None):
    """뉴스 관련성 점수 계산 (0~10). 높을수록 핵심 기사."""
    text = (title + " " + desc).lower()
    score = 0
    # 펀드 직접 언급 (핵심)
    fund_hits = sum(1 for k in fund_kws if k.lower() in text)
    score += fund_hits * 3
    # 투자 활동 키워드
    invest_kws = [
        "투자","운용","배분","포트폴리오","대체투자","사모","인프라","부동산","펀드",
        "investment","portfolio","allocation","private equity","infrastructure",
        "real estate","fund","acquisition","stake","commit","약정","위탁",
        "직접투자","co-investment","수익률","returns","performance","deal","딜",
    ]
    invest_hits = sum(1 for k in invest_kws if k in text)
    score += min(invest_hits, 4)
    # 자산군 키워드 (보너스)
    if asset_kws:
        score += sum(1 for k in asset_kws if k.lower() in text)
    # 노이즈 패널티
    noise_kws = [
        "주주총회","사외이사","횡령","배임","소송","고려아연","영풍","경영권",
        "라이다","주가","주식","ipo","상장","스팩","etf 투자설명서",
    ]
    noise_hits = sum(1 for k in noise_kws if k in text)
    score -= noise_hits * 3
    return max(score, 0)

def fetch_fund_news(fund, top_n=5):
    """기관별 상세 전용: 관련성 높은 뉴스만 상위 top_n개 반환"""
    kws = NEWS_KEYWORDS.get(fund, [])
    asset_kws = []
    for kw_list in ASSET_KEYWORDS.values():
        asset_kws.extend(kw_list[:2])
    # 추가 투자 특화 키워드 조합
    invest_combos = [f"{kws[0]} 투자", f"{kws[0]} 운용", f"{kws[0]} 대체투자"]
    all_kws = kws + invest_combos
    raw = fetch_news(all_kws[:6])
    # 관련성 점수 계산 및 정렬
    scored = []
    for art in raw:
        s = score_news_relevance(art["title"], art["description"], kws, asset_kws)
        if s >= 3:  # 최소 점수 3점 이상만 포함
            scored.append((s, art))
    scored.sort(key=lambda x: -x[0])
    # 해외 뉴스 추가
    try:
        global_arts = fetch_global_rss(extra_kw=kws)
        for art in global_arts[:3]:
            s = score_news_relevance(art["title"], art["description"], kws)
            if s >= 2:
                scored.append((s + 1, art))  # 해외 뉴스 보너스
    except Exception:
        pass
    scored.sort(key=lambda x: -x[0])
    return [art for _, art in scored[:top_n]]

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
    prompt = f"""당신은 글로벌 연기금 대체투자 전략을 분석하는 한국 기관투자자의 CIO 어드바이저입니다.
아래 5개 글로벌 연기금(국민연금·CPPIB·CalPERS·OTPP·PSP)의 최신 자산군별 배분 데이터를 분석하고,
한국 보험사·연기금 투자 담당자에게 실질적으로 유용한 인사이트를 JSON으로만 반환하세요.

분석 기준:
- 각 자산군의 글로벌 트렌드 방향성(확대/축소/유지)과 그 배경
- 기관 간 전략 차별점과 시사점
- 한국 기관투자자 관점에서의 구체적 액션 아이템

JSON 형식 (모든 값은 한국어, 2～3문장 분량):
{{
  "headline": "<글로벌 연기금 대체투자 흐름의 핵심 메시지 2문장. 수치 포함>",
  "pe_signal": "<PE 트렌드: 누가 왜 축소/확대하는지, 한국 기관에 주는 시사점>",
  "credit_signal": "<Private Credit 트렌드: 금리 환경 연계 분석, 구체적 기회>",
  "infra_signal": "<인프라 트렌드: 에너지전환·디지털인프라 중심으로 기회와 리스크>",
  "re_signal": "<부동산 트렌드: 오피스 리스크 vs 물류·주거 기회, 현시점 판단>",
  "key_movers": [
    "<기관명: 가장 큰 배분 변화와 전략적 의미>",
    "<기관명: 두 번째 주목할 변화>"
  ],
  "opportunity": "<한국 기관투자자가 지금 당장 검토해야 할 가장 구체적인 투자 기회. 자산군·지역·전략 포함>",
  "risk": "<현재 글로벌 연기금 포트폴리오에서 가장 우려되는 리스크. 선행 지표와 대응 방안 포함>"
}}

배분 데이터: {json.dumps(matrix_json, ensure_ascii=False)}"""
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

# CSS  ── 라이트 메인 / 다크 사이드바
st.markdown("""
<style>
/* ── 사이드바만 다크 ── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background-color: #0f1923 !important;
}
[data-testid="stSidebar"] * { color: #dce6f0 !important; }

/* ── 탭 ── */
[data-testid="stTabs"] button {
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 6px 16px !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #1d4ed8 !important;
    border-bottom: 2px solid #3b82f6 !important;
    font-weight: 700 !important;
}

/* ── 기관 개요 카드 (라이트 버전) ── */
.metric-card {
    background: #f0f7ff;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 4px solid #3b82f6;
    margin-bottom: 8px;
    color: #1e293b;
    line-height: 1.8;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.metric-card b { color: #0f172a; }

/* ── 기관 헤더 배너 ── */
.fund-header {
    background: linear-gradient(90deg, #1e3a5f, #1e40af);
    border-radius: 8px;
    padding: 14px 20px;
    margin-bottom: 16px;
    color: #f1f5f9;
}
.fund-header span { color: #f1f5f9 !important; }

/* ── 뱃지 ── */
.badge-alt       { background:#dbeafe; color:#1d4ed8;  padding:3px 9px; border-radius:5px; font-size:12px; font-weight:700; }
.badge-fund      { background:#dcfce7; color:#15803d;  padding:3px 9px; border-radius:5px; font-size:12px; font-weight:700; }
.badge-risk-red  { background:#fee2e2; color:#b91c1c;  padding:3px 9px; border-radius:5px; font-size:12px; font-weight:700; }
.badge-risk-yel  { background:#fef3c7; color:#b45309;  padding:3px 9px; border-radius:5px; font-size:12px; font-weight:700; }
.badge-risk-grn  { background:#dcfce7; color:#15803d;  padding:3px 9px; border-radius:5px; font-size:12px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ── 차트 공통 설정 (라이트 테마 기준) ────────────────────────
CHART_BG   = "#f8fafc"        # 차트 내부 배경: 연한 회색
PAPER_BG   = "rgba(0,0,0,0)"  # 외곽 투명
GRID_COLOR = "#e2e8f0"        # 그리드: 연한 선
TICK_COLOR = "#1e293b"        # 축 레이블: 진한 색
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

# ── 세션 초기화 ──────────────────────────────────────────────
if "page_sel"  not in st.session_state: st.session_state["page_sel"]  = "🏠 Radar 메인"
if "nav_fund"  not in st.session_state: st.session_state["nav_fund"]  = None

with st.sidebar:
    st.markdown("## 📡 Pension Alt Radar")
    st.markdown("---")
    page = st.radio("", [
        "🏠 Radar 메인",
        "🏦 기관별 상세",
        "📊 자산군별 비교",
        "📰 News · Issues · Deals",
        "📁 Data Room",
    ], key="page_sel", label_visibility="collapsed")
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
<p style='font-size:10px;color:#4a5568;margin-top:4px'>★ 본 분석 대상 | 2024～2025 연차보고서 기준</p>
"""
    st.markdown(ranking_html, unsafe_allow_html=True)
    st.markdown("---")
    st.caption("📌 분석 기관 바로가기")
    FUND_NAV = {
        "🇰🇷 국민연금(NPS)": "국민연금(NPS)",
        "🇺🇸 CalPERS":       "CalPERS",
        "🇨🇦 CPPIB":         "CPPIB",
        "🇨🇦 PSP":           "PSP Investments",
        "🇨🇦 OTPP":          "OTPP",
    }
    for label, fund_key in FUND_NAV.items():
        if st.button(label, key=f"nav_btn_{fund_key}", use_container_width=True):
            st.session_state["page_sel"] = "🏦 기관별 상세"
            st.session_state["nav_fund"] = fund_key
            st.rerun()

# ══════════════════════════════════════════════════════════════
# PAGE 1: RADAR 메인
# ══════════════════════════════════════════════════════════════

if page == "🏠 Radar 메인":
    st.title("📡 Institutional Pension Alt Radar")
    st.caption("글로벌 연기금 대체투자 배분 흐름 분석 대시보드")

    # ── KPI 카드 ──────────────────────────────────────────────
    all_articles = fetch_news([kw for kws in NEWS_KEYWORDS.values() for kw in kws[:1]])
    tagged_all = []
    for a in all_articles:
        ftags, atags = tag_article(a["title"], a["description"])
        risk_lv = risk_level(a["title"], a["description"])
        tagged_all.append({**a, "fund_tags": ftags, "asset_tags": atags, "risk": risk_lv})

    n_news       = len(tagged_all)
    n_asset_iss  = len([a for a in tagged_all if a["asset_tags"]])
    n_high_alert = len([a for a in tagged_all if a["risk"] == "🔴 High"])
    top_asset    = "–"
    if tagged_all:
        from collections import Counter
        ac = Counter(a for art in tagged_all for a in art["asset_tags"])
        top_asset = ac.most_common(1)[0][0] if ac else "–"

    kpi_cols = st.columns(5)
    kpi_data = [
        ("🏦 분석기관", str(len(FUNDS)), "개"),
        ("📰 최근 뉴스", str(n_news), "건 (30일)"),
        ("📊 자산군 이슈", str(n_asset_iss), "건"),
        ("🔴 High Alert", str(n_high_alert), "건"),
        ("🏆 최다 이슈 자산군", top_asset, ""),
    ]
    for col, (label, val, unit) in zip(kpi_cols, kpi_data):
        with col:
            st.markdown(
                f"<div style='background:#f0f7ff;border-left:4px solid #3b82f6;"
                f"border-radius:8px;padding:12px 14px;margin-bottom:6px'>"
                f"<p style='font-size:11px;color:#64748b;margin:0 0 4px'>{label}</p>"
                f"<p style='font-size:22px;font-weight:800;color:#1d4ed8;margin:0'>{val}"
                f"<span style='font-size:12px;font-weight:400;color:#475569'> {unit}</span></p>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.divider()

    # ── 배분 매트릭스 (y=기관, x=자산군) ─────────────────────
    st.subheader("🗺 Pension Fund Flow Map")
    st.caption("y축=기관 / x축=자산군 | 색상: 대체투자(파랑 강조) / 일반(회색)")

    # 헤더
    mx = "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
    mx += "<thead><tr style='background:#1e293b'>"
    mx += "<th style='padding:10px 12px;text-align:left;color:#94a3b8;width:160px'>기관</th>"
    for ac in ALT_CLASSES:
        short = ac.replace("Private ","P.").replace("Hedge Fund/","HF/")
        mx += f"<th style='padding:8px 6px;text-align:center;color:#93c5fd;font-size:12px'>{short}</th>"
    for ac in ["Public Equity","Fixed Income"]:
        short = ac.replace("Public ","Pub.").replace("Fixed ","FI ")
        mx += f"<th style='padding:8px 6px;text-align:center;color:#94a3b8;font-size:12px'>{short}</th>"
    mx += "<th style='padding:8px 12px;text-align:center;color:#93c5fd;font-size:12px'>Alt합계</th>"
    mx += "<th style='padding:8px 12px;text-align:left;color:#64748b;font-size:11px'>기관 특징</th>"
    mx += "</tr></thead><tbody>"

    for fi, fund in enumerate(FUNDS):
        m    = FUND_META[fund]
        sig  = INST_SIGNAL.get(fund,"")
        char = FUND_CHARACTERISTIC.get(fund,"")
        sig_color = "#b91c1c" if "🔴" in sig else ("#b45309" if "🟡" in sig else "#15803d")
        row_bg = "#f8fafc" if fi % 2 == 0 else "#ffffff"
        # 시그널 배지 (컴팩트)
        sig_parts = sig.split("—")
        sig_badge = sig_parts[0].strip() if sig_parts else sig
        sig_detail = sig_parts[1].strip()[:60] if len(sig_parts) > 1 else ""

        mx += f"<tr style='background:{row_bg};border-bottom:2px solid #e2e8f0;vertical-align:top'>"
        mx += (f"<td style='padding:12px 14px;min-width:170px;max-width:190px'>"
               f"<b style='color:#0f172a;font-size:13px'>{fund}</b><br>"
               f"<span style='font-size:10px;color:#94a3b8'>{m['country']} | {m['type']}</span><br>"
               f"<span style='font-size:10px;color:#64748b'>AUM: {m['aum']}</span><br>"
               f"<span style='display:inline-block;margin-top:5px;font-size:10px;font-weight:700;"
               f"color:{sig_color};background:{'#fef2f2' if '🔴' in sig else ('#fffbeb' if '🟡' in sig else '#f0fdf4')};"
               f"padding:2px 7px;border-radius:10px'>{sig_badge}</span>"
               f"</td>")
        # ALT_CLASSES
        alt_sum = 0
        for ac in ALT_CLASSES:
            cur, pre = ALLOC[fund].get(ac,(None,None))
            arr = delta_arrow(cur,pre)
            d   = (cur-pre) if cur and pre else 0
            ac_col = "#15803d" if d>0.3 else ("#b91c1c" if d<-0.3 else "#64748b")
            cell = f"<b style='color:#1d4ed8'>{pct_badge(cur)}</b><br><span style='font-size:10px;color:{ac_col}'>{arr}</span>"
            mx += f"<td style='padding:8px 6px;text-align:center;background:#f0f7ff'>{cell}</td>"
            if cur: alt_sum += cur
        # Non-alt
        for ac in ["Public Equity","Fixed Income"]:
            cur, pre = ALLOC[fund].get(ac,(None,None))
            arr = delta_arrow(cur,pre)
            d   = (cur-pre) if cur and pre else 0
            ac_col = "#15803d" if d>0.3 else ("#b91c1c" if d<-0.3 else "#64748b")
            cell = f"<b style='color:#334155'>{pct_badge(cur)}</b><br><span style='font-size:10px;color:{ac_col}'>{arr}</span>"
            mx += f"<td style='padding:8px 6px;text-align:center'>{cell}</td>"
        # Alt합계
        alt_pre_sum = sum(ALLOC[fund][a][1] for a in ALT_CLASSES if ALLOC[fund].get(a,(None,None))[1])
        alt_d = alt_sum - alt_pre_sum
        alt_col = "#15803d" if alt_d>0.2 else ("#b91c1c" if alt_d<-0.2 else "#64748b")
        alt_arr = f"{'▲+' if alt_d>0 else '▼'}{abs(alt_d):.1f}%p"
        mx += (f"<td style='padding:8px 6px;text-align:center;background:#eff6ff'>"
               f"<b style='font-size:15px;color:#1d4ed8'>{alt_sum:.1f}%</b><br>"
               f"<span style='font-size:10px;color:{alt_col}'>{alt_arr}</span></td>")
        # 기관 특징
        # 기관 특징 - 첫 문장 굵게(두괄식), 이후 2문장 일반
        char_sentences = [s.strip() for s in char.replace('. ', '.|').split('|') if s.strip() and len(s.strip()) > 5]
        char_html = ""
        for ci2, sent in enumerate(char_sentences[:3]):
            weight = "700" if ci2 == 0 else "400"
            col2   = "#0f172a" if ci2 == 0 else "#475569"
            size   = "12.5px" if ci2 == 0 else "11.5px"
            char_html += f"<p style='margin:0 0 5px;font-size:{size};font-weight:{weight};color:{col2};line-height:1.6'>{sent}.</p>"
        mx += f"<td style='padding:10px 16px;vertical-align:top;min-width:260px;word-break:keep-all;word-wrap:break-word'>{char_html}</td>"
        mx += "</tr>"

    mx += "</tbody></table>"
    st.markdown(mx, unsafe_allow_html=True)
    st.caption("※ OTPP는 레버리지 포함 이펙티브 자산믹스 기준(합계>100%). NPS 대체 세부비중은 대체투자 구성비 환산값.")

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
        c1, c2 = st.columns(2)
        with c1:
            for k, label in [("pe_signal","PE"),("credit_signal","Credit"),
                              ("infra_signal","Infra"),("re_signal","Real Estate")]:
                st.markdown(f"**{label}:** {ai_r.get(k,'')}")
        with c2:
            st.markdown(f"**🎯 기회:** {ai_r.get('opportunity','')}")
            st.markdown(f"**⚠️ 리스크:** {ai_r.get('risk','')}")
    else:
        st.caption("버튼을 클릭하면 AI 종합 해석이 표시됩니다.")

    # ── 기관별 최근 이슈 표 ─────────────────────────────────
    st.divider()
    st.subheader("💬 기관별 최근 이슈 현황")
    issue_rows = []
    for fund in FUNDS:
        fund_arts = [a for a in tagged_all if fund in a.get("fund_tags",[])]
        n_dedup   = len({a["title"] for a in fund_arts})
        issue_rows.append({
            "기관": fund,
            "직접 뉴스(건)": n_dedup,
            "최근 이슈 요약": RECENT_ISSUES.get(fund,"–")[:80]+"…" if len(RECENT_ISSUES.get(fund,""))>80 else RECENT_ISSUES.get(fund,"–"),
            "시그널": INST_SIGNAL.get(fund,"").split("—")[0].strip() if INST_SIGNAL.get(fund) else "–",
        })
    df_issues = pd.DataFrame(issue_rows)
    st.dataframe(df_issues, use_container_width=True, hide_index=True)

    # ── 대체투자 자산군 이슈 ─────────────────────────────────
    st.divider()
    st.subheader("📌 대체투자 자산군 이슈")
    ac_colors = {
        "Private Equity":   "#3b82f6",
        "Private Credit":   "#8b5cf6",
        "Infrastructure":   "#10b981",
        "Real Estate":      "#f59e0b",
        "Hedge Fund/Other": "#6366f1",
    }
    for ac in ALT_CLASSES:
        ov      = ASSET_OVERVIEW.get(ac, {})
        ac_arts = [a for a in tagged_all if ac in a.get("asset_tags", [])]
        n_ac    = len({a["title"] for a in ac_arts})
        top_c   = ac_colors.get(ac, "#3b82f6")
        # 관련 기관 (현재 비중 상위 3개)
        ac_funds = sorted(FUNDS, key=lambda f: ALLOC[f].get(ac,(0,0))[0] or 0, reverse=True)[:3]
        fund_tags = " ".join(
            f"<span style='background:#dbeafe;color:#1d4ed8;font-size:10px;font-weight:600;"
            f"padding:1px 6px;border-radius:8px;margin-right:3px'>{f}</span>"
            for f in ac_funds
        )
        with st.expander(f"**{ac}** — 관련 뉴스 {n_ac}건", expanded=True):
            st.markdown(
                f"<div style='border-left:4px solid {top_c};padding:0 0 0 14px'>"
                f"<p style='font-size:13px;color:#334155;line-height:1.75;margin:0 0 10px'>"
                f"<b style='color:#0f172a'>개요:</b> {ov.get('overview','')}</p>"
                f"<div style='display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px'>"
                f"<div style='flex:1;min-width:200px'>"
                f"<p style='font-size:11px;font-weight:700;color:#15803d;margin:0 0 3px'>✅ 투자 매력</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.65;margin:0'>{ov.get('attraction','')}</p>"
                f"</div>"
                f"<div style='flex:1;min-width:200px'>"
                f"<p style='font-size:11px;font-weight:700;color:#b91c1c;margin:0 0 3px'>⚠️ 주요 리스크</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.65;margin:0'>{ov.get('risk','')}</p>"
                f"</div>"
                f"</div>"
                f"<div style='background:#fffbeb;border-left:3px solid #f59e0b;border-radius:0 6px 6px 0;"
                f"padding:8px 12px;margin-bottom:10px'>"
                f"<p style='font-size:11px;font-weight:700;color:#b45309;margin:0 0 3px'>🔔 최근 이슈</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.65;margin:0'>{ov.get('recent','')}</p>"
                f"</div>"
                f"<p style='font-size:11px;color:#64748b;margin:0'>주요 투자 기관: {fund_tags}</p>"
                f"</div>",
                unsafe_allow_html=True
            )
            # 관련 뉴스 (있는 경우)
            if ac_arts:
                st.markdown("**관련 뉴스**")
                for art in ac_arts[:3]:
                    src_badge = f"[{art.get('source','Naver')}]" if art.get('is_global') else ""
                    st.markdown(
                        f"• {src_badge} [{art['title'][:80]}]({art.get('link','#')})  "
                        f"<span style='font-size:11px;color:#94a3b8'>{art.get('pubDate','')[:16]}</span>",
                        unsafe_allow_html=True
                    )


# ══════════════════════════════════════════════════════════════
# PAGE 2: 기관별 상세
# ══════════════════════════════════════════════════════════════

elif page == "🏦 기관별 상세":
    st.title("🏦 기관별 상세")

    # nav_fund가 설정된 경우 해당 기관을 첫 번째 탭으로 이동 (→ 자동 활성화)
    nav_fund = st.session_state.get("nav_fund")
    if nav_fund and nav_fund in FUNDS:
        ordered_funds = [nav_fund] + [f for f in FUNDS if f != nav_fund]
        st.session_state["nav_fund"] = None  # 소비 후 초기화
    else:
        ordered_funds = FUNDS

    fund_tabs = st.tabs(ordered_funds)

    for tab_idx, tab in enumerate(fund_tabs):
        fund = ordered_funds[tab_idx]
        meta   = FUND_META[fund]
        alloc  = ALLOC[fund]
        ret_ts = RETURNS_TS[fund]
        issue  = RECENT_ISSUES[fund]

        with tab:
            # ── 기관 개요 카드 ───────────────────────────────────
            alt_cur_v  = sum(v[0] for k,v in alloc.items() if k in ALT_CLASSES and v[0])
            last_ret_k = list(ret_ts.keys())[-1]
            last_ret_v = ret_ts[last_ret_k]
            core_assets = [a for a in ALT_CLASSES if alloc.get(a,(0,0))[0] and alloc[a][0] >= 5.0]
            core_str    = " / ".join(core_assets) if core_assets else "다각화"
            sig         = INST_SIGNAL.get(fund, "")
            sig_color   = "#b91c1c" if "🔴" in sig else ("#b45309" if "🟡" in sig else "#15803d")
            char        = FUND_CHARACTERISTIC.get(fund, "")

            # 5년 CAGR 계산
            ret_vals = list(ret_ts.values())
            cagr_val = None
            if len(ret_vals) >= 5:
                from functools import reduce
                product = reduce(lambda a, b: a * (1 + b/100), ret_vals[-5:], 1.0)
                cagr_val = (product ** (1/5) - 1) * 100

            st.markdown(f"""
<div style='background:linear-gradient(135deg,#1e3a8a,#1d4ed8);border-radius:12px;
            padding:20px 24px;margin-bottom:16px;color:#f1f5f9'>
  <div style='display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px'>
    <div>
      <p style='font-size:22px;font-weight:800;color:#ffffff;margin:0 0 4px'>{fund}</p>
      <p style='font-size:13px;color:#bfdbfe;margin:0'>{meta['country']} | {meta['type']}</p>
      <p style='font-size:12px;color:#93c5fd;margin:6px 0 0'>{char}</p>
    </div>
    <div style='display:flex;gap:20px;flex-wrap:wrap'>
      <div style='text-align:center'>
        <p style='font-size:11px;color:#93c5fd;margin:0'>총 운용자산</p>
        <p style='font-size:16px;font-weight:700;color:#ffffff;margin:2px 0'>{meta['aum']}</p>
      </div>
      <div style='text-align:center'>
        <p style='font-size:11px;color:#93c5fd;margin:0'>대체투자 비중</p>
        <p style='font-size:20px;font-weight:800;color:#fbbf24;margin:2px 0'>{alt_cur_v:.1f}%</p>
      </div>
      <div style='text-align:center'>
        <p style='font-size:11px;color:#93c5fd;margin:0'>핵심 자산군</p>
        <p style='font-size:13px;font-weight:600;color:#a5f3fc;margin:2px 0'>{core_str}</p>
      </div>
      <div style='text-align:center'>
        <p style='font-size:11px;color:#93c5fd;margin:0'>최근 수익률 ({last_ret_k})</p>
        <p style='font-size:20px;font-weight:800;color:{"#86efac" if last_ret_v>=0 else "#fca5a5"};margin:2px 0'>{last_ret_v:+.1f}%</p>
      </div>
      {"<div style='text-align:center'><p style='font-size:11px;color:#93c5fd;margin:0'>5년 연평균(CAGR)</p><p style='font-size:16px;font-weight:700;color:#ffffff;margin:2px 0'>"+f"{cagr_val:.1f}%"+"</p></div>" if cagr_val else ""}
    </div>
  </div>
  <div style='margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.2)'>
    <span style='font-size:12px;font-weight:700;color:{sig_color};background:rgba(255,255,255,0.1);
                 padding:3px 10px;border-radius:12px'>{sig}</span>
  </div>
</div>""", unsafe_allow_html=True)

            # ── 연도별 자산배분 + 대체투자 변화 ─────────────────────
            asset_color_map = {
                "Private Equity":"#3b82f6","Private Credit":"#8b5cf6",
                "Infrastructure":"#10b981","Real Estate":"#f59e0b",
                "Hedge Fund/Other":"#6366f1","Public Equity":"#475569","Fixed Income":"#64748b",
            }

            # 해당 기관의 연도 목록 (정규화)
            fund_ts = ALLOC_TS.get(fund, {})
            fund_yr_keys = list(fund_ts.keys())          # 원본 키 (FY포함)
            fund_yrs     = [norm_year(y) for y in fund_yr_keys]  # 정규화

            st.markdown(
                "<p style='font-size:15px;font-weight:700;color:#1d4ed8;margin:4px 0 8px'>"
                "📅 연도별 자산배분 현황</p>",
                unsafe_allow_html=True
            )
            alloc_yr_tabs = st.tabs(fund_yrs)

            for yi, yr_tab in enumerate(alloc_yr_tabs):
                sel_raw = fund_yr_keys[yi]          # 원본 키
                sel_yr  = fund_yrs[yi]              # 정규화 연도
                with yr_tab:
                    yr_alloc_data = fund_ts.get(sel_raw, {})
                    # 전기 데이터
                    prev_raw  = fund_yr_keys[yi-1] if yi > 0 else None
                    prev_data = fund_ts.get(prev_raw, {}) if prev_raw else {}

                    c1, c2 = st.columns([1.4, 1])

                    with c1:
                        bar_labels = ALL_CLASSES
                        bar_values = [yr_alloc_data.get(a, 0) for a in bar_labels]
                        bar_colors = [asset_color_map.get(a,"#64748b") for a in bar_labels]
                        fig_bar = go.Figure(go.Bar(
                            y=bar_labels, x=bar_values,
                            orientation="h",
                            marker_color=bar_colors,
                            text=[f"{v:.1f}%" for v in bar_values],
                            textposition="outside",
                            textfont=dict(size=12, color="#1e293b"),
                            cliponaxis=False,
                        ))
                        max_v = max(bar_values) if bar_values else 10
                        fig_bar.update_layout(
                            title=dict(text=f"{fund} {sel_yr}년 자산배분",
                                       font=dict(color="#475569", size=13)),
                            paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                            font=dict(color=TICK_COLOR, size=12),
                            xaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%",
                                       range=[0, max_v*1.35],
                                       tickfont=dict(color=TICK_COLOR, size=11)),
                            yaxis=dict(tickfont=dict(color="#1e293b", size=12),
                                       categoryorder="array",
                                       categoryarray=list(reversed(bar_labels))),
                            margin=dict(l=10, r=70, t=36, b=10),
                            height=300, showlegend=False,
                        )
                        st.plotly_chart(fig_bar, use_container_width=True,
                                        key=f"hbar_{fund}_{sel_yr}")

                    with c2:
                        prev_label = norm_year(prev_raw) if prev_raw else None
                        hdr = (f"전기({prev_label}) 대비 변화" if prev_label
                               else f"{sel_yr}년 대체투자 비중")
                        st.markdown(
                            f"<p style='font-size:14px;font-weight:700;color:#1d4ed8;"
                            f"margin-bottom:10px'>대체투자 비중 변화 ({hdr})</p>",
                            unsafe_allow_html=True
                        )
                        for a in ALT_CLASSES:
                            cur_v = yr_alloc_data.get(a, 0)
                            pre_v = prev_data.get(a) if prev_data else None
                            d = round(cur_v - pre_v, 1) if pre_v is not None else None
                            d_col  = "#15803d" if (d and d>0.1) else ("#b91c1c" if (d and d<-0.1) else "#64748b")
                            d_icon = "▲" if (d and d>0.1) else ("▼" if (d and d<-0.1) else "→")
                            d_str  = f"{d_icon} {abs(d):.1f}%p" if d is not None else "–"
                            bar_pct = min(cur_v / 30 * 100, 100)
                            ac_col  = asset_color_map.get(a, "#64748b")
                            st.markdown(f"""
<div style='margin-bottom:12px'>
  <div style='display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px'>
    <span style='font-size:12px;font-weight:600;color:#475569'>{a}</span>
    <span>
      <span style='font-size:15px;font-weight:700;color:#0f172a'>{cur_v:.1f}%</span>
      &nbsp;<span style='font-size:12px;color:{d_col};font-weight:600'>{d_str}</span>
    </span>
  </div>
  <div style='background:#e2e8f0;border-radius:4px;height:7px;overflow:hidden'>
    <div style='background:{ac_col};width:{bar_pct:.1f}%;height:100%;border-radius:4px'></div>
  </div>
</div>""", unsafe_allow_html=True)

            st.divider()

            # ── 5개년 전체 자산배분 스택 바 (alt 라인·합계 바 통합) ───
            st.markdown("<p style='font-size:16px;font-weight:700;color:#1d4ed8;margin:12px 0 6px'>📊 전체 자산배분 5개년 변화 (스택)</p>", unsafe_allow_html=True)
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

                # ── 연도별 리밸런싱 분석 탭 ────────────────────────────
                st.markdown(
                    "<p style='font-size:16px;font-weight:700;color:#1d4ed8;margin:16px 0 8px'>"
                    "🔄 연도별 리밸런싱 분석</p>",
                    unsafe_allow_html=True
                )
                if len(raw_years2) >= 2:
                    year_pairs  = [(raw_years2[i], raw_years2[i+1]) for i in range(len(raw_years2)-1)]
                    pair_labels = [f"{norm_year(a)} → {norm_year(b)}" for a,b in year_pairs]
                    rebal_tabs  = st.tabs(pair_labels)

                    for ri, (rtab, (yr_from, yr_to)) in enumerate(zip(rebal_tabs, year_pairs)):
                        with rtab:
                            fa = alloc_ts_fund2[yr_from]
                            ta = alloc_ts_fund2[yr_to]
                            chg = {cls: round(ta.get(cls,0) - fa.get(cls,0), 1) for cls in ALL_CLASSES}
                            inc_l = sorted([(c,d) for c,d in chg.items() if d > 0.1], key=lambda x:-x[1])
                            dec_l = sorted([(c,d) for c,d in chg.items() if d < -0.1], key=lambda x:x[1])
                            a_s   = sum(fa.get(c,0) for c in ALT_CLASSES)
                            a_e   = sum(ta.get(c,0) for c in ALT_CLASSES)
                            a_d   = round(a_e - a_s, 1)
                            a_col = "#15803d" if a_d > 0 else ("#b91c1c" if a_d < 0 else "#64748b")
                            a_arr = "▲" if a_d > 0 else ("▼" if a_d < 0 else "→")

                            # 요약 헤더
                            st.markdown(
                                f"<div style='background:#f8fafc;border:1px solid #e2e8f0;"
                                f"border-radius:8px;padding:12px 16px;margin-bottom:12px;"
                                f"font-size:13px;color:#334155'>"
                                f"대체투자 합계: <b style='color:#1e293b'>{a_s:.1f}%</b>"
                                f" → <b style='color:{a_col};font-size:15px'>{a_e:.1f}%</b>"
                                f"&nbsp;<span style='color:{a_col};font-weight:700'>"
                                f"{a_arr} {abs(a_d):.1f}%p</span></div>",
                                unsafe_allow_html=True
                            )

                            # 확대 / 축소 2컬럼
                            inc_html = "".join(
                                f"<div style='padding:5px 0;border-bottom:1px solid #f1f5f9'>"
                                f"<span style='font-size:12px;color:#475569;font-weight:600'>{c}</span><br>"
                                f"<span style='font-size:13px;color:#1e293b'>"
                                f"{fa.get(c,0):.1f}% → {ta.get(c,0):.1f}%</span>"
                                f"&nbsp;<span style='color:#15803d;font-weight:700;font-size:13px'>"
                                f"(+{d:.1f}%p)</span></div>"
                                for c,d in inc_l
                            ) or "<span style='color:#94a3b8;font-size:12px'>변동 없음</span>"

                            dec_html = "".join(
                                f"<div style='padding:5px 0;border-bottom:1px solid #f1f5f9'>"
                                f"<span style='font-size:12px;color:#475569;font-weight:600'>{c}</span><br>"
                                f"<span style='font-size:13px;color:#1e293b'>"
                                f"{fa.get(c,0):.1f}% → {ta.get(c,0):.1f}%</span>"
                                f"&nbsp;<span style='color:#b91c1c;font-weight:700;font-size:13px'>"
                                f"({d:.1f}%p)</span></div>"
                                for c,d in dec_l
                            ) or "<span style='color:#94a3b8;font-size:12px'>변동 없음</span>"

                            col_l, col_r = st.columns(2)
                            with col_l:
                                st.markdown(
                                    "<p style='font-size:12px;font-weight:700;color:#15803d;"
                                    "margin:0 0 6px'>📈 비중 확대</p>"
                                    f"<div style='font-size:13px'>{inc_html}</div>",
                                    unsafe_allow_html=True
                                )
                            with col_r:
                                st.markdown(
                                    "<p style='font-size:12px;font-weight:700;color:#b91c1c;"
                                    "margin:0 0 6px'>📉 비중 축소</p>"
                                    f"<div style='font-size:13px'>{dec_html}</div>",
                                    unsafe_allow_html=True
                                )

                            # 기간별 해설
                            nkey = (norm_year(yr_from), norm_year(yr_to))
                            yearly = REBAL_YEARLY.get(fund, {}).get(nkey, {})
                            if yearly:
                                t_title = yearly.get("title","")
                                t_text  = yearly.get("text","")
                                st.markdown(
                                    f"<div style='margin-top:14px;padding:14px 18px;"
                                    f"background:#f0f7ff;border-left:4px solid #3b82f6;"
                                    f"border-radius:0 8px 8px 0;font-size:13.5px;line-height:1.8;"
                                    f"color:#1e293b'>"
                                    f"<p style='font-weight:700;color:#1d4ed8;margin:0 0 8px'>"
                                    f"📝 {t_title}</p>"
                                    f"<p style='margin:0'>{t_text}</p>"
                                    f"<p style='font-size:11px;color:#94a3b8;margin:8px 0 0'>"
                                    f"※ 회계연도: NPS·OTPP(12월말) / CPPIB·PSP(3월말) / CalPERS(6월말)</p>"
                                    f"</div>",
                                    unsafe_allow_html=True
                                )

            st.divider()

            # ── 수익률·성과 추이 ─────────────────────────────────
            st.markdown(
                "<p style='font-size:16px;font-weight:700;color:#1d4ed8;margin:4px 0 8px'>"
                "📈 수익률·성과 분석</p>",
                unsafe_allow_html=True
            )
            c3, c4 = st.columns([1.3, 1])

            with c3:
                # 수익률 바차트 + BM 비교
                ret_years  = list(ret_ts.keys())
                ret_vals_l = list(ret_ts.values())
                bm_ts_fund = BENCHMARK_TS.get(fund, {})

                fig_ret = go.Figure()
                # 수익률 바
                bar_colors_ret = ["#15803d" if v >= 0 else "#b91c1c" for v in ret_vals_l]
                fig_ret.add_trace(go.Bar(
                    x=ret_years, y=ret_vals_l,
                    name="수익률",
                    marker_color=bar_colors_ret,
                    text=[f"{v:+.1f}%" for v in ret_vals_l],
                    textposition="outside",
                    textfont=dict(color="#1e293b", size=11),
                ))
                # BM 라인 (있는 연도만)
                bm_x = [yr for yr in ret_years if norm_year(yr) in {norm_year(k) for k in bm_ts_fund}]
                bm_y_map = {norm_year(k): v for k, v in bm_ts_fund.items()}
                bm_y = [bm_y_map.get(norm_year(yr)) for yr in bm_x if bm_y_map.get(norm_year(yr)) is not None]
                bm_x_f = [yr for yr in bm_x if bm_y_map.get(norm_year(yr)) is not None]
                if bm_x_f:
                    fig_ret.add_trace(go.Scatter(
                        x=bm_x_f, y=bm_y,
                        name="벤치마크",
                        mode="lines+markers",
                        line=dict(color="#f59e0b", width=2, dash="dash"),
                        marker=dict(size=6),
                    ))
                fig_ret.update_layout(
                    title=dict(text=f"{fund} 수익률 추이 (BM 포함)", font=dict(color="#475569", size=13)),
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12),
                    legend=dict(font=dict(color=TICK_COLOR, size=11), bgcolor="rgba(0,0,0,0)"),
                    yaxis=dict(gridcolor=GRID_COLOR, ticksuffix="%",
                               tickfont=dict(color=TICK_COLOR)),
                    xaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(color=TICK_COLOR)),
                    barmode="group",
                )
                fig_ret.add_hline(y=0, line_color="#94a3b8", line_width=1)
                st.plotly_chart(fig_ret, use_container_width=True, key=f"ret_{fund}")
                bm_note = {
                    "국민연금(NPS)":   "📌 BM 출처: 금융부문 TWR 기준 (보건복지부·NPS 연차보고서 공시)",
                    "CPPIB":           "📌 BM: 연차보고서 미공시 (부가가치 누적 VA만 공시) — 그래프에서 BM 라인 생략",
                    "CalPERS":         "📌 BM 출처: Policy Portfolio 기준 (FY2022·FY2023·FY2025만 공시, 나머지 연도 생략)",
                    "OTPP":            "📌 BM 출처: Reference Portfolio 기준 (OTPP 연차보고서, 레버리지 포함 이펙티브 믹스 BM)",
                    "PSP Investments": "📌 BM 출처: Reference Portfolio 기준 (PSP 연차보고서, FY2021～FY2025 전 기간 공시)",
                }
                st.caption(bm_note.get(fund, ""))

            with c4:
                # 성과 지표 + 분석 멘트
                ret_vals_all = list(ret_ts.values())
                avg_5 = sum(ret_vals_all[-5:]) / min(5, len(ret_vals_all)) if ret_vals_all else 0
                best_yr  = max(ret_ts, key=ret_ts.get)
                worst_yr = min(ret_ts, key=ret_ts.get)
                pos_yrs  = sum(1 for v in ret_vals_all if v >= 0)

                # CAGR
                from functools import reduce as _reduce
                cagr5 = None
                if len(ret_vals_all) >= 5:
                    prod = _reduce(lambda a, b: a*(1+b/100), ret_vals_all[-5:], 1.0)
                    cagr5 = (prod**(1/5)-1)*100

                # BM 초과 성과
                bm_excess_pairs = []
                for yr, ret_v in ret_ts.items():
                    bm_v = bm_y_map.get(norm_year(yr))
                    if bm_v is not None:
                        bm_excess_pairs.append((yr, round(ret_v - bm_v, 1)))
                avg_excess = sum(v for _,v in bm_excess_pairs)/len(bm_excess_pairs) if bm_excess_pairs else None

                # 성과 카드
                kpis = [
                    ("5년 평균 수익률", f"{avg_5:.1f}%", "#1d4ed8"),
                    ("5년 CAGR", f"{cagr5:.1f}%" if cagr5 else "–", "#1d4ed8"),
                    ("최고 수익 연도", f"{best_yr} ({ret_ts[best_yr]:+.1f}%)", "#15803d"),
                    ("최저 수익 연도", f"{worst_yr} ({ret_ts[worst_yr]:+.1f}%)", "#b91c1c"),
                    ("BM 평균 초과", f"{avg_excess:+.1f}%p" if avg_excess is not None else "미공시", "#b45309"),
                    ("플러스 연도 수", f"{pos_yrs}/{len(ret_vals_all)}년", "#475569"),
                ]
                kpi_html = "<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px'>"
                for label, val, col in kpis:
                    kpi_html += (f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
                                 f"padding:8px 10px'>"
                                 f"<p style='font-size:10px;color:#64748b;margin:0'>{label}</p>"
                                 f"<p style='font-size:14px;font-weight:700;color:{col};margin:2px 0'>{val}</p>"
                                 f"</div>")
                kpi_html += "</div>"
                st.markdown(kpi_html, unsafe_allow_html=True)

                # 배분-성과 연계 분석
                alloc_ts_f = ALLOC_TS.get(fund, {})
                last_raw  = list(alloc_ts_f.keys())[-1]  if alloc_ts_f else None
                first_raw = list(alloc_ts_f.keys())[0]   if alloc_ts_f else None
                alt_delta_perf = None
                if last_raw and first_raw:
                    a_s2 = sum(alloc_ts_f[first_raw].get(c,0) for c in ALT_CLASSES)
                    a_e2 = sum(alloc_ts_f[last_raw].get(c,0)  for c in ALT_CLASSES)
                    alt_delta_perf = round(a_e2 - a_s2, 1)

                perf_comment = []
                if cagr5:
                    perf_comment.append(
                        f"최근 5년 CAGR <b style='color:#1d4ed8'>{cagr5:.1f}%</b>로 "
                        f"{'장기 목표 수준 충족' if cagr5 >= 7 else '목표 수익률 하회 — 포트폴리오 점검 필요'}."
                    )
                if alt_delta_perf is not None:
                    direction = "확대" if alt_delta_perf > 0 else "축소"
                    perf_comment.append(
                        f"같은 기간 대체투자 비중 <b style='color:#{'15803d' if alt_delta_perf>0 else 'b91c1c'}'>"
                        f"{alt_delta_perf:+.1f}%p {direction}</b> — "
                        f"{'대체투자 확대가 안정적 초과수익 창출에 기여한 것으로 판단' if alt_delta_perf>0 else '유동성 선호 전환 또는 밸류에이션 압박에 따른 조정'}."
                    )
                if avg_excess is not None:
                    perf_comment.append(
                        f"BM 대비 평균 <b style='color:#{'15803d' if avg_excess>0 else 'b91c1c'}'>"
                        f"{avg_excess:+.1f}%p {'초과' if avg_excess>0 else '하회'}</b> — "
                        f"{'액티브 운용 역량 확인' if avg_excess>0 else '패시브 대비 추가 비용·리스크 검토 필요'}."
                    )

                if perf_comment:
                    st.markdown(
                        "<div style='background:#f0f7ff;border-left:4px solid #3b82f6;"
                        "border-radius:0 8px 8px 0;padding:12px 14px;font-size:13px;"
                        "color:#1e293b;line-height:1.8'>"
                        "<p style='font-weight:700;color:#1d4ed8;margin:0 0 6px'>📌 배분-성과 연계 분석</p>"
                        + "<br>".join(perf_comment) +
                        "</div>",
                        unsafe_allow_html=True
                    )

            st.divider()
            # 기관 특징 & 이슈 (간소화)
            c5, c6 = st.columns(2)
            with c5:
                st.markdown("<p style='font-size:14px;font-weight:700;color:#1d4ed8'>기관 특징 & 운용 방향</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:13px;color:#334155;line-height:1.7'>{meta['description']}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size:13px;color:#475569;line-height:1.7;margin-top:8px'>{meta['strategy']}</p>", unsafe_allow_html=True)
            with c6:
                st.markdown("<p style='font-size:14px;font-weight:700;color:#b45309'>⚡ 최근 이슈</p>", unsafe_allow_html=True)
                st.markdown(f"<div style='background:#fffbeb;border-left:3px solid #f59e0b;border-radius:4px;padding:10px 14px;font-size:13px;color:#78350f;line-height:1.7'>{issue}</div>", unsafe_allow_html=True)

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

            # 관련 뉴스 (관련성 점수 필터링)
            st.divider()
            st.markdown("##### 📰 관련 뉴스")
            st.caption("투자·운용 활동 관련 기사만 선별 표시 (관련성 낮은 기사 자동 제외)")
            with st.spinner("뉴스 수집 중..."):
                arts = fetch_fund_news(fund, top_n=6)
            if not arts:
                st.info("관련성 높은 뉴스가 없습니다. (네이버 API 키 설정 또는 해외 RSS 연결 확인)")
            for a in arts:
                src_badge = f"🌐 [{a.get('source','')}]" if a.get("is_global") else "📰"
                risk_lv   = risk_level(a["title"], a["description"])
                risk_col  = "#b91c1c" if "High" in risk_lv else ("#b45309" if "Medium" in risk_lv else "#15803d")
                with st.expander(f"{src_badge} {a['title'][:85]}"):
                    st.markdown(
                        f"<span style='font-size:11px;color:{risk_col};font-weight:600'>{risk_lv}</span>"
                        f"&nbsp;|&nbsp;<span style='font-size:11px;color:#64748b'>{a.get('pubDate','')[:16]}</span>",
                        unsafe_allow_html=True
                    )
                    st.write(a["description"])
                    if a.get("link"): st.markdown(f"[원문 보기]({a['link']})")

# ══════════════════════════════════════════════════════════════
# PAGE 3: 자산군별 비교
# ══════════════════════════════════════════════════════════════

elif page == "📊 자산군별 비교":
    st.title("📊 자산군별 비교")

    all_ts_years = sorted(set(
        norm_year(yr) for f in FUNDS for yr in ALLOC_TS.get(f, {}).keys()
    ), key=lambda x: int(x))

    fund_color_map = {
        "국민연금(NPS)":"#f59e0b","CPPIB":"#3b82f6",
        "CalPERS":"#10b981","OTPP":"#8b5cf6","PSP Investments":"#f43f5e",
    }

    asset_tabs = st.tabs(ALT_CLASSES)

    for tab_idx, tab in enumerate(asset_tabs):
        asset = ALT_CLASSES[tab_idx]
        ov = ASSET_OVERVIEW.get(asset, {})

        with tab:
            # ── (1) 자산군 개요 ────────────────────────────────
            st.markdown(
                f"<div style='background:#f0f7ff;border-left:4px solid #3b82f6;"
                f"border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:16px'>"
                f"<p style='font-size:15px;font-weight:700;color:#1d4ed8;margin:0 0 8px'>{asset} 개요</p>"
                f"<p style='font-size:13px;color:#334155;margin:0 0 6px'>{ov.get('overview','')}</p>"
                f"<div style='display:flex;gap:16px;margin-top:10px;flex-wrap:wrap'>"
                f"<div style='flex:1;min-width:200px'>"
                f"<p style='font-size:11px;font-weight:700;color:#15803d;margin:0 0 3px'>✅ 투자 매력</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.6;margin:0'>{ov.get('attraction','')}</p>"
                f"</div>"
                f"<div style='flex:1;min-width:200px'>"
                f"<p style='font-size:11px;font-weight:700;color:#b91c1c;margin:0 0 3px'>⚠️ 주요 리스크</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.6;margin:0'>{ov.get('risk','')}</p>"
                f"</div>"
                f"<div style='flex:1;min-width:200px'>"
                f"<p style='font-size:11px;font-weight:700;color:#b45309;margin:0 0 3px'>🔔 최근 이슈</p>"
                f"<p style='font-size:12px;color:#1e293b;line-height:1.6;margin:0'>{ov.get('recent','')}</p>"
                f"</div>"
                f"</div></div>",
                unsafe_allow_html=True
            )

            # ── (2) 연도별 기관 비중 비교 ──────────────────────
            st.markdown(
                "<p style='font-size:15px;font-weight:700;color:#1d4ed8;margin:4px 0 8px'>"
                "📅 연도별 기관 비중 비교</p>",
                unsafe_allow_html=True
            )
            yr_tabs = st.tabs(all_ts_years)

            for yi, yr_tab in enumerate(yr_tabs):
                sel_yr = all_ts_years[yi]
                with yr_tab:
                    yr_rows = []
                    for fund in FUNDS:
                        yr_map = {norm_year(k): v for k, v in ALLOC_TS.get(fund, {}).items()}
                        cur = yr_map.get(sel_yr, {}).get(asset)
                        pre_yr = str(int(sel_yr) - 1)
                        pre = yr_map.get(pre_yr, {}).get(asset)
                        delta = round(cur - pre, 1) if (cur is not None and pre is not None) else None
                        yr_rows.append({
                            "기관": fund,
                            "비중(%)": cur,
                            "전기(%)": pre,
                            "증감(pp)": delta,
                        })

                    df_yr = pd.DataFrame(yr_rows)
                    df_yr_v = df_yr.dropna(subset=["비중(%)"]).sort_values("비중(%)", ascending=False).copy()
                    df_yr_v["순위"] = range(1, len(df_yr_v)+1)

                    if df_yr_v.empty:
                        st.caption(f"{sel_yr}년 데이터 없음")
                        continue

                    # 통합 순위표 + 기관 특징
                    tbl = ("<table style='width:100%;border-collapse:collapse;font-size:13px'>"
                           "<thead><tr style='background:#f8fafc;border-bottom:2px solid #e2e8f0'>"
                           "<th style='padding:8px 10px;color:#64748b;text-align:center;width:36px'>#</th>"
                           "<th style='padding:8px 10px;color:#1e293b;text-align:left'>기관</th>"
                           f"<th style='padding:8px 10px;color:#1d4ed8;text-align:right'>{sel_yr}년 비중</th>"
                           "<th style='padding:8px 10px;color:#64748b;text-align:right'>전기 비중</th>"
                           "<th style='padding:8px 10px;color:#64748b;text-align:right'>증감</th>"
                           ""
                           "</tr></thead><tbody>")

                    for _, row in df_yr_v.iterrows():
                        d = row["증감(pp)"]
                        d_valid = d is not None and d == d
                        d_col = "#15803d" if (d_valid and d>0) else ("#b91c1c" if (d_valid and d<0) else "#64748b")
                        d_str = f"{'▲+' if d>0 else '▼'}{abs(d):.1f}pp" if d_valid else "–"
                        pre_str = f"{row['전기(%)']:.1f}%" if pd.notna(row['전기(%)']) else "–"
                        bg = "#f0f7ff" if _ % 2 == 0 else "#ffffff"
                        fund_color = fund_color_map.get(row['기관'], '#64748b')
                        tbl += (f"<tr style='background:{bg};border-bottom:1px solid #f1f5f9'>"
                                f"<td style='padding:8px 10px;text-align:center;font-weight:700;color:#94a3b8'>{int(row['순위'])}</td>"
                                f"<td style='padding:8px 10px;font-weight:600;color:#1e293b'>"
                                f"<span style='display:inline-block;width:10px;height:10px;border-radius:50%;"
                                f"background:{fund_color};margin-right:6px'></span>{row['기관']}</td>"
                                f"<td style='padding:8px 10px;text-align:right;font-size:15px;font-weight:700;color:#1d4ed8'>{row['비중(%)']:.1f}%</td>"
                                f"<td style='padding:8px 10px;text-align:right;color:#64748b'>{pre_str}</td>"
                                f"<td style='padding:8px 10px;text-align:right;font-weight:600;color:{d_col}'>{d_str}</td>"
                                ""
                                f"</tr>")
                    tbl += "</tbody></table>"
                    st.markdown(tbl, unsafe_allow_html=True)

            st.divider()

            # ── (3) 연도별 비중 요약표 (히트맵) ───────────────────
            st.markdown(
                f"<p style='font-size:15px;font-weight:700;color:#1d4ed8;margin:4px 0 8px'>"
                f"📋 {asset} 연도별 비중 요약표</p>"
                f"<p style='font-size:12px;color:#64748b;margin:0 0 10px'>"
                f"셀 색상이 짙을수록 비중 높음 | 행=기관, 열=연도</p>",
                unsafe_allow_html=True
            )
            ts5_rows = []
            for f in FUNDS:
                for yr, yr_alloc in ALLOC_TS.get(f, {}).items():
                    val = yr_alloc.get(asset)
                    if val is not None:
                        ts5_rows.append({"연도": norm_year(yr), "기관": f, "비중(%)": val})

            if ts5_rows:
                df_ts5 = pd.DataFrame(ts5_rows)
                df_pivot = df_ts5.pivot(index="기관", columns="연도", values="비중(%)")
                df_pivot = df_pivot.reindex([f for f in FUNDS if f in df_pivot.index])
                sorted_cols = sorted(df_pivot.columns, key=lambda x: int(x))
                df_pivot = df_pivot[sorted_cols]

                fig_heat = go.Figure(go.Heatmap(
                    z=df_pivot.values.tolist(),
                    x=list(df_pivot.columns),
                    y=list(df_pivot.index),
                    colorscale=[[0,"#f0f7ff"],[0.5,"#3b82f6"],[1,"#1e3a8a"]],
                    text=[[f"{v:.1f}%" if (v==v) else "–" for v in row] for row in df_pivot.values],
                    texttemplate="%{text}",
                    textfont=dict(size=12, color="#1e293b"),
                    showscale=True,
                    colorbar=dict(title=dict(text="%", font=dict(color=TICK_COLOR)),
                                  tickfont=dict(color=TICK_COLOR), thickness=12, len=0.8),
                    hovertemplate="<b>%{y}</b><br>%{x}년<br>비중: <b>%{text}</b><extra></extra>",
                ))
                fig_heat.update_layout(
                    paper_bgcolor=PAPER_BG, plot_bgcolor=CHART_BG,
                    font=dict(color=TICK_COLOR, size=12), height=250,
                    margin=dict(l=0, r=60, t=30, b=10),
                    xaxis=dict(side="top", tickfont=dict(color=TICK_COLOR, size=12)),
                    yaxis=dict(tickfont=dict(color=TICK_COLOR, size=12)),
                )
                st.plotly_chart(fig_heat, use_container_width=True, key=f"heat_{asset}")

                # 히트맵 코멘트
                # 최다 비중 기관 & 최근 변화 큰 기관 자동 분석
                if not df_pivot.empty:
                    last_col = sorted_cols[-1]
                    prev_col = sorted_cols[-2] if len(sorted_cols) > 1 else None
                    max_fund = df_pivot[last_col].idxmax() if last_col in df_pivot.columns else "–"
                    max_val  = df_pivot[last_col].max() if last_col in df_pivot.columns else 0
                    comment_parts = [
                        f"<b style='color:#1d4ed8'>{last_col}년 기준</b> 최고 비중 기관은 "
                        f"<b>{max_fund}</b> ({max_val:.1f}%)."
                    ]
                    if prev_col:
                        chg_series = df_pivot[last_col] - df_pivot[prev_col]
                        chg_series = chg_series.dropna()
                        if not chg_series.empty:
                            inc_fund = chg_series.idxmax()
                            dec_fund = chg_series.idxmin()
                            inc_val  = chg_series.max()
                            dec_val  = chg_series.min()
                            if inc_val > 0.1:
                                comment_parts.append(
                                    f"전기 대비 가장 크게 <b style='color:#15803d'>확대</b>한 기관: "
                                    f"<b>{inc_fund}</b> (+{inc_val:.1f}%p)."
                                )
                            if dec_val < -0.1:
                                comment_parts.append(
                                    f"가장 크게 <b style='color:#b91c1c'>축소</b>한 기관: "
                                    f"<b>{dec_fund}</b> ({dec_val:.1f}%p)."
                                )
                    st.markdown(
                        f"<div style='background:#f8fafc;border-left:3px solid #3b82f6;"
                        f"border-radius:0 6px 6px 0;padding:10px 14px;margin-top:8px;"
                        f"font-size:13px;color:#334155;line-height:1.7'>"
                        + " ".join(comment_parts) + "</div>",
                        unsafe_allow_html=True
                    )

            st.divider()

            # ── (4) 자산군 특징 & 전략 방향 ────────────────────────
            c3, c4 = st.columns([1, 1])
            with c3:
                st.markdown("##### 자산군 특징")
                st.markdown(f"<div style='background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:12px 16px;font-size:13px;color:#1e293b;line-height:1.75'>{ASSET_SUMMARY.get(asset,'').replace(chr(126),'～')}</div>", unsafe_allow_html=True)
            with c4:
                st.markdown("##### 기관별 현재 전략 방향")
                for fund in FUNDS:
                    cur_v, pre_v = ALLOC[fund].get(asset,(None,None))
                    d = (cur_v - pre_v) if cur_v and pre_v else 0
                    direction = "📈 확대" if d > 0.5 else ("📉 축소" if d < -0.5 else "➡ 유지")
                    char_full = FUND_CHARACTERISTIC.get(fund, "")
                    char_s1 = char_full.split(". ")[0] if char_full else ""
                    st.markdown(
                        f"<div style='padding:5px 0;border-bottom:1px solid #f1f5f9'>"
                        f"<b>{fund}</b>: {pct_badge(cur_v)} {direction}"
                        f"<br><span style='font-size:11.5px;color:#475569;line-height:1.6'>{char_s1}.</span></div>",
                        unsafe_allow_html=True
                    )

            # ── (5) AI 분석 ──────────────────────────────────────
            st.divider()
            if st.button("🧠 AI 자산군 비교 분석", key=f"ai_asset_btn_{asset}"):
                data = {f: ALLOC[f].get(asset,(None,None)) for f in FUNDS}
                data_json = json.dumps(
                    {f: {"cur": v[0], "pre": v[1]} for f, v in data.items()},
                    ensure_ascii=False
                )
                asset_summary = ASSET_SUMMARY.get(asset, "")
                prompt = (
                    f"분석 자산군: {asset}\n"
                    f"기관별 현재/전기 비중: {data_json}\n"
                    f"전략 특징: {asset_summary}\n"
                    "JSON 반환:\n"
                    "JSON 반환:\n"
                    '{"leader":"<선도 기관>","laggard":"<뒤처지는 기관>","trend":"<전반적 트렌드>",'
                    '"opportunity":"<한국 기관투자자 관점 기회>","caution":"<주의사항>"}'
                )
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

    c1, c2, c3 = st.columns(3)
    with c1: fund_filter  = st.multiselect("기관 필터", ["전체"]+FUNDS, default=["전체"])
    with c2: asset_filter = st.multiselect("자산군 필터", ["전체"]+ALT_CLASSES, default=["전체"])
    with c3: risk_filter  = st.multiselect("리스크 필터", ["전체","🔴 High","🟡 Medium","🟢 Low"], default=["전체"])

    all_kws = []
    for kws in NEWS_KEYWORDS.values(): all_kws.extend(kws[:1])
    for kws in ASSET_KEYWORDS.values(): all_kws.extend(kws[:1])

    if st.button("🔄 뉴스 새로고침"):
        st.cache_data.clear()

    with st.spinner("뉴스 수집 중..."):
        articles = fetch_news(all_kws)

    if not articles:
        st.info("Naver API 키가 없으면 뉴스가 표시되지 않습니다.")

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
        src_label    = f"[{art.get('source','')}] " if art.get("is_global") else ""
        with st.expander(f"{src_label}{art['title'][:80]}…" if len(art["title"])>80 else f"{src_label}{art['title']}"):
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
    st.info("OpenAI API 키가 설정되어야 AI 수치 추출이 작동합니다. Render 환경변수에 OPENAI_API_KEY를 추가하세요.")

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
                df_edit = pd.DataFrame({"자산군":list(alloc_dr),"AI 추출 (%)": [round(v,1) for v in alloc_dr.values()],"검수 수정 (%)": [round(v,1) for v in alloc_dr.values()]})
                edited = st.data_editor(df_edit, key=f"edit_{item['file']}", use_container_width=True, hide_index=True)
                if st.button("✅ 대시보드에 반영", key=f"save_{item['file']}"):
                    saved = st.session_state.get("dr_saved",{})
                    saved[(item.get("fund_name",""), item.get("report_year",""))] = dict(zip(edited["자산군"], edited["검수 수정 (%)"]))
                    st.session_state["dr_saved"] = saved
                    st.success("저장 완료!")
            else:
                st.warning("배분 데이터를 추출하지 못했습니다.")

    saved = st.session_state.get("dr_saved",{})
    if saved:
        st.divider()
        st.markdown("##### ✅ 검수 완료 데이터")
        for (fn, yr), alloc_s in saved.items():
            st.markdown(f"• **{fn} ({yr})** – {len(alloc_s)}개 항목")
