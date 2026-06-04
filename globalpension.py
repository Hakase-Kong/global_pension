"""
globalpension.py
────────────────────────────────────────────────────────────────
글로벌 연기금 / 국부펀드 투자 데이터 뷰어
  - Allocation Detail (자산배분 %)
  - Geographic Exposure (국가별 익스포져)
  - Returns by Asset Class (asset class별 수익률)
  - Multi-Year Returns (다년도 수익률 추이)

실행: python globalpension.py
"""

# ══════════════════════════════════════════════════════════════
# 1. 데이터 정의
# ══════════════════════════════════════════════════════════════

# ── 1-A. 자산배분 % ───────────────────────────────────────────
ALLOCATION_DETAIL = [
    {"fund":"CPP Investments","year":"FY2025","aum":714.4,"currency":"CAD B",
     "equity_total":0.58,"public_equity":0.29,"private_equity":0.29,
     "fixed_income":0.15,"real_estate":0.07,"infrastructure":0.09,
     "credit":0.11,"alternatives":None,"cash_other":None,
     "notes":"Real Estate + Infra 별도 집계"},
    {"fund":"CPP Investments","year":"FY2026","aum":793.3,"currency":"CAD B",
     "equity_total":0.58,"public_equity":0.36,"private_equity":0.22,
     "fixed_income":0.13,"real_estate":None,"infrastructure":None,
     "credit":0.09,"alternatives":None,"cash_other":None,
     "notes":"FY2026부터 Real Assets 통합 20%"},
    {"fund":"OTPP","year":"2024","aum":266.3,"currency":"CAD B",
     "equity_total":0.41,"public_equity":0.14,"private_equity":0.23,
     "fixed_income":0.30,"real_estate":0.11,"infrastructure":0.17,
     "credit":0.14,"alternatives":0.09,"cash_other":None,
     "notes":"ARS(절대수익) 9% 별도"},
    {"fund":"OTPP","year":"2025","aum":279.4,"currency":"CAD B",
     "equity_total":0.43,"public_equity":0.18,"private_equity":0.19,
     "fixed_income":0.23,"real_estate":0.10,"infrastructure":0.13,
     "credit":0.14,"alternatives":0.09,"cash_other":0.20,
     "notes":"Venture Growth 6% 포함; 인플레이션민감 20%"},
    {"fund":"PSP Investments","year":"FY2024","aum":264.9,"currency":"CAD B",
     "equity_total":None,"public_equity":0.21,"private_equity":0.153,
     "fixed_income":0.212,"real_estate":0.103,"infrastructure":0.130,
     "credit":0.099,"alternatives":None,"cash_other":0.066,
     "notes":"자연자원 6.6% 포함"},
    {"fund":"PSP Investments","year":"FY2025","aum":299.7,"currency":"CAD B",
     "equity_total":None,"public_equity":None,"private_equity":0.136,
     "fixed_income":None,"real_estate":0.089,"infrastructure":0.107,
     "credit":0.101,"alternatives":None,"cash_other":0.077,
     "notes":"Capital Markets 48.7%; 자연자원 6.0%"},
    {"fund":"NZ Super Fund","year":"FY2024","aum":76.65,"currency":"NZD B",
     "equity_total":0.50,"public_equity":0.46,"private_equity":0.03,
     "fixed_income":0.21,"real_estate":0.05,"infrastructure":0.05,
     "credit":None,"alternatives":0.07,"cash_other":0.13,
     "notes":"Rural/Timber 5% 포함"},
    {"fund":"NZ Super Fund","year":"FY2025","aum":85.1,"currency":"NZD B",
     "equity_total":0.54,"public_equity":0.50,"private_equity":0.05,
     "fixed_income":0.18,"real_estate":0.05,"infrastructure":0.04,
     "credit":None,"alternatives":0.08,"cash_other":0.11,
     "notes":"Rural/Timber 5% 포함"},
    {"fund":"CDPQ","year":"2024","aum":473.3,"currency":"CAD B",
     "equity_total":0.466,"public_equity":0.275,"private_equity":0.191,
     "fixed_income":0.328,"real_estate":0.089,"infrastructure":0.136,
     "credit":0.217,"alternatives":None,"cash_other":0.009,
     "notes":"Rates 10.3% + Credit 21.7% = FI 32.8%"},
    {"fund":"CDPQ (La Caisse)","year":"2025","aum":517.3,"currency":"CAD B",
     "equity_total":0.456,"public_equity":0.292,"private_equity":0.164,
     "fixed_income":0.341,"real_estate":0.083,"infrastructure":0.144,
     "credit":0.233,"alternatives":None,"cash_other":0.011,
     "notes":"Rates 10.2% + Credit 23.3% = FI 34.1%"},
    {"fund":"Future Fund","year":"FY2024","aum":224.9,"currency":"AUD B",
     "equity_total":0.373,"public_equity":0.270,"private_equity":0.145,
     "fixed_income":None,"real_estate":0.054,"infrastructure":0.099,
     "credit":0.110,"alternatives":0.152,"cash_other":0.067,
     "notes":"호주 주식 10.3% 포함"},
    {"fund":"Future Fund","year":"FY2025","aum":252.3,"currency":"AUD B",
     "equity_total":0.423,"public_equity":0.325,"private_equity":0.133,
     "fixed_income":None,"real_estate":0.044,"infrastructure":0.114,
     "credit":0.089,"alternatives":0.147,"cash_other":0.051,
     "notes":"호주 주식 10.8% 포함"},
    {"fund":"GPFG (Norway)","year":"2024","aum":19742,"currency":"NOK B",
     "equity_total":0.714,"public_equity":0.714,"private_equity":None,
     "fixed_income":0.266,"real_estate":0.018,"infrastructure":0.001,
     "credit":None,"alternatives":None,"cash_other":0.002,
     "notes":"비상장 RE 1.8%; 상장 RE 별도"},
    {"fund":"GPFG (Norway)","year":"2025","aum":21268,"currency":"NOK B",
     "equity_total":0.713,"public_equity":0.713,"private_equity":None,
     "fixed_income":0.265,"real_estate":0.017,"infrastructure":0.004,
     "credit":None,"alternatives":None,"cash_other":0.004,
     "notes":"인프라 3배 증가 (태양광·풍력)"},
    {"fund":"CalPERS","year":"FY2025","aum":634.6,"currency":"USD B",
     "equity_total":0.393,"public_equity":0.258,"private_equity":0.156,
     "fixed_income":0.270,"real_estate":0.074,"infrastructure":0.033,
     "credit":None,"alternatives":None,"cash_other":0.034,
     "notes":"민간부채 3.4% 포함"},
]

# ── 1-B. 국가별 익스포져 ─────────────────────────────────────
GEOGRAPHIC_EXPOSURE = [
    {"fund":"CPP Investments","year":"FY2025",
     "usa":0.47,"canada":0.12,"europe":0.19,"asia_pacific":0.17,
     "latin_america":0.05,"australia":None,"other":None,
     "notes":"5개년 추이: US 36→36→38→42→47%"},
    {"fund":"CPP Investments","year":"FY2026",
     "usa":0.48,"canada":0.12,"europe":0.17,"asia_pacific":0.18,
     "latin_america":0.05,"australia":None,"other":None,
     "notes":"비캐나다 비중 78%"},
    {"fund":"OTPP","year":"2025",
     "usa":0.38,"canada":0.31,"europe":0.18,"asia_pacific":0.08,
     "latin_america":0.05,"australia":None,"other":None,
     "notes":"USD $117B, EMEA $56B, APAC $26B, LatAm $17B"},
    {"fund":"PSP Investments","year":"FY2025",
     "usa":0.405,"canada":0.200,"europe":0.163,"asia_pacific":0.113,
     "latin_america":None,"australia":0.055,"other":0.064,
     "notes":"총 투자자산 기준; Oceania 5.5%"},
    {"fund":"NZ Super Fund","year":"FY2024",
     "north_america":0.541,"new_zealand":0.106,
     "usa":None,"canada":None,"europe":0.196,"asia_pacific":0.079,
     "latin_america":None,"australia":0.038,"other":0.040,
     "notes":"북미 54.1%, NZ 10.6%, Japan 4.2%"},
    {"fund":"NZ Super Fund","year":"FY2025",
     "north_america":0.571,"new_zealand":0.113,
     "usa":None,"canada":None,"europe":0.181,"asia_pacific":0.081,
     "latin_america":None,"australia":0.024,"other":0.030,
     "notes":"북미 57.1%, NZ 11.3%, Japan 3.5%"},
    {"fund":"CDPQ","year":"2024",
     "usa":0.38,"canada":0.30,"europe":0.15,"asia_pacific":0.10,
     "latin_america":0.04,"australia":None,"other":0.03,
     "notes":"65개국 이상 투자"},
    {"fund":"CDPQ (La Caisse)","year":"2025",
     "usa":0.38,"canada":0.29,"europe":0.17,"asia_pacific":0.10,
     "latin_america":0.04,"australia":None,"other":0.02,
     "notes":"퀘벡 자산 $100B 달성"},
    {"fund":"Future Fund","year":"FY2024",
     "usa":0.43,"canada":None,"europe":0.15,"asia_pacific":0.06,
     "latin_america":None,"australia":0.21,"other":0.10,
     "notes":"물리적 소재지 기준; EM 10%, 개발도상국 4%"},
    {"fund":"Future Fund","year":"FY2025",
     "usa":0.43,"canada":None,"europe":0.15,"asia_pacific":0.06,
     "latin_america":None,"australia":0.23,"other":0.10,
     "notes":"물리적 소재지 기준; EM 10%, 개발도상국 4%"},
    {"fund":"GPFG (Norway)","year":"2024",
     "north_america":0.569,
     "usa":0.534,"canada":None,"europe":0.252,"asia_pacific":0.142,
     "latin_america":0.005,"australia":0.020,"other":0.007,
     "notes":"북미 56.9%; 중동 0.4%, 아프리카 0.3%"},
    {"fund":"GPFG (Norway)","year":"2025",
     "north_america":0.560,
     "usa":0.529,"canada":None,"europe":0.258,"asia_pacific":0.145,
     "latin_america":0.005,"australia":0.019,"other":0.008,
     "notes":"북미 56.0%; 중동 0.4%, 아프리카 0.4%"},
    {"fund":"CalPERS","year":"FY2025",
     "usa":None,"canada":None,"europe":None,"asia_pacific":None,
     "latin_america":None,"australia":None,"other":None,
     "notes":"국내주식 $163.8B / 해외주식 $79.7B (세부 지역 미공개)"},
]

# ── 1-C. Asset Class별 수익률 ────────────────────────────────
RETURNS_BY_ASSET_CLASS = [
    {"fund":"CPP Investments","year":"FY2025",
     "total":0.093,"public_equity":0.106,"private_equity":0.118,
     "fixed_income":0.081,"real_estate":0.038,"infrastructure":0.094,
     "credit":0.144,"alternatives":None,"real_assets":None,
     "notes":"Credit +14.4% 최고; RE +3.8%"},
    {"fund":"CPP Investments","year":"FY2026",
     "total":0.078,"public_equity":0.175,"private_equity":0.029,
     "fixed_income":-0.001,"real_estate":0.037,"infrastructure":0.112,
     "credit":0.037,"alternatives":None,"real_assets":0.122,
     "notes":"Sust.Energy +23.2%; Infra +11.2%; RE +3.7%"},
    {"fund":"OTPP","year":"2025",
     "total":0.067,"public_equity":0.150,"private_equity":-0.053,
     "fixed_income":0.026,"real_estate":-0.031,"infrastructure":0.018,
     "credit":0.058,"alternatives":None,"real_assets":-0.004,
     "notes":"Venture Growth +30.2%; 벤치마크 대비 -5.0%"},
    {"fund":"PSP Investments","year":"FY2024",
     "total":0.072,"public_equity":0.175,"private_equity":0.121,
     "fixed_income":0.029,"real_estate":-0.159,"infrastructure":0.143,
     "credit":0.142,"alternatives":None,"real_assets":None,
     "notes":"RE -15.9% (오피스 평가손); Infra +14.3%"},
    {"fund":"PSP Investments","year":"FY2025",
     "total":0.126,"public_equity":None,"private_equity":None,
     "fixed_income":None,"real_estate":None,"infrastructure":None,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"하이라이트만 공개; 5yr 10.6%, 10yr 8.2%"},
    {"fund":"NZ Super Fund","year":"FY2024",
     "total":0.149,"public_equity":None,"private_equity":None,
     "fixed_income":None,"real_estate":None,"infrastructure":None,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"Reference Portfolio 15.13%; Value add -0.24%"},
    {"fund":"NZ Super Fund","year":"FY2025",
     "total":0.1184,"public_equity":None,"private_equity":None,
     "fixed_income":None,"real_estate":None,"infrastructure":None,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"Reference Portfolio 10.87%; Value add +0.98%"},
    {"fund":"CDPQ","year":"2024",
     "total":0.094,"public_equity":0.255,"private_equity":0.172,
     "fixed_income":0.018,"real_estate":-0.108,"infrastructure":0.095,
     "credit":0.008,"alternatives":None,"real_assets":None,
     "notes":"RE -10.8%; 5yr 총수익 6.2%"},
    {"fund":"CDPQ (La Caisse)","year":"2025",
     "total":0.093,"public_equity":0.177,"private_equity":0.023,
     "fixed_income":0.005,"real_estate":0.002,"infrastructure":0.092,
     "credit":0.096,"alternatives":None,"real_assets":None,
     "notes":"Credit +9.6%; Infra +9.2%; 5yr 6.5%"},
    {"fund":"Future Fund","year":"FY2024",
     "total":0.091,"public_equity":None,"private_equity":None,
     "fixed_income":None,"real_estate":None,"infrastructure":None,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"자산군별 수익률 미공개 (전체 펀드만 발표)"},
    {"fund":"Future Fund","year":"FY2025",
     "total":0.122,"public_equity":None,"private_equity":None,
     "fixed_income":None,"real_estate":None,"infrastructure":None,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"자산군별 수익률 미공개 (전체 펀드만 발표)"},
    {"fund":"GPFG (Norway)","year":"2024",
     "total":0.1309,"public_equity":0.1819,"private_equity":None,
     "fixed_income":0.0128,"real_estate":-0.0057,"infrastructure":-0.0981,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"펀드 통화 바스켓 기준; Infra -9.81%"},
    {"fund":"GPFG (Norway)","year":"2025",
     "total":0.1511,"public_equity":0.1929,"private_equity":None,
     "fixed_income":0.0542,"real_estate":0.0436,"infrastructure":0.1807,
     "credit":None,"alternatives":None,"real_assets":None,
     "notes":"펀드 통화 바스켓 기준; Infra +18.07%"},
    {"fund":"CalPERS","year":"FY2025",
     "total":0.116,"public_equity":0.168,"private_equity":0.143,
     "fixed_income":0.065,"real_estate":0.028,"infrastructure":None,
     "credit":0.128,"alternatives":None,"real_assets":None,
     "notes":"PE/민간부채는 Mar 2025 기준; 벤치마크 +1.7%p 초과"},
]

# ── 1-D. 다년도 수익률 추이 ──────────────────────────────────
MULTI_YEAR_RETURNS = [
    {"fund":"CPP Investments FY2026","currency":"CAD","yr_1":0.078,"yr_1_prior":0.093,"yr_5":0.066,"yr_10":0.088,"since_inception":None,"fy_end":"Mar 31"},
    {"fund":"CPP Investments FY2025","currency":"CAD","yr_1":0.093,"yr_1_prior":0.080,"yr_5":0.090,"yr_10":0.083,"since_inception":None,"fy_end":"Mar 31"},
    {"fund":"OTPP 2025",             "currency":"CAD","yr_1":0.067,"yr_1_prior":0.094,"yr_5":0.066,"yr_10":0.068,"since_inception":0.092,"fy_end":"Dec 31"},
    {"fund":"PSP Investments FY2025","currency":"CAD","yr_1":0.126,"yr_1_prior":0.072,"yr_5":0.106,"yr_10":0.082,"since_inception":None,"fy_end":"Mar 31"},
    {"fund":"PSP Investments FY2024","currency":"CAD","yr_1":0.072,"yr_1_prior":None, "yr_5":0.079,"yr_10":0.083,"since_inception":None,"fy_end":"Mar 31"},
    {"fund":"NZ Super Fund FY2025",  "currency":"NZD","yr_1":0.1184,"yr_1_prior":0.149,"yr_5":0.1162,"yr_10":0.1006,"since_inception":0.1009,"fy_end":"Jun 30"},
    {"fund":"NZ Super Fund FY2024",  "currency":"NZD","yr_1":0.149,"yr_1_prior":0.126,"yr_5":0.0952,"yr_10":0.1033,"since_inception":0.1000,"fy_end":"Jun 30"},
    {"fund":"CDPQ 2025",             "currency":"CAD","yr_1":0.093,"yr_1_prior":0.094,"yr_5":0.065,"yr_10":0.072,"since_inception":None,"fy_end":"Dec 31"},
    {"fund":"CDPQ 2024",             "currency":"CAD","yr_1":0.094,"yr_1_prior":0.072,"yr_5":0.062,"yr_10":0.071,"since_inception":None,"fy_end":"Dec 31"},
    {"fund":"Future Fund FY2025",    "currency":"AUD","yr_1":0.122,"yr_1_prior":0.091,"yr_5":0.094,"yr_10":0.080,"since_inception":0.079,"fy_end":"Jun 30"},
    {"fund":"Future Fund FY2024",    "currency":"AUD","yr_1":0.091,"yr_1_prior":0.082,"yr_5":0.067,"yr_10":0.083,"since_inception":0.077,"fy_end":"Jun 30"},
    {"fund":"GPFG (Norway) 2025",    "currency":"NOK","yr_1":0.1511,"yr_1_prior":0.1309,"yr_5":0.0826,"yr_10":0.0847,"since_inception":0.0664,"fy_end":"Dec 31"},
    {"fund":"GPFG (Norway) 2024",    "currency":"NOK","yr_1":0.1309,"yr_1_prior":0.1614,"yr_5":0.0744,"yr_10":0.0725,"since_inception":0.0634,"fy_end":"Dec 31"},
    {"fund":"CalPERS FY2025",        "currency":"USD","yr_1":0.116,"yr_1_prior":None, "yr_5":0.080,"yr_10":0.071,"since_inception":None,"fy_end":"Jun 30"},
]


# ══════════════════════════════════════════════════════════════
# 2. 출력 헬퍼
# ══════════════════════════════════════════════════════════════

def pct(v):
    if v is None:
        return "    -   "
    return f"{v*100:+6.2f}%"

def pct_plain(v):
    if v is None:
        return "  -  "
    return f"{v*100:.1f}%"

def divider(char="─", n=72):
    print(char * n)

def header(title):
    divider("═")
    print(f"  {title}")
    divider("═")

def sub_header(title):
    divider("─", 50)
    print(f"  {title}")
    divider("─", 50)


# ══════════════════════════════════════════════════════════════
# 3. 뷰 함수
# ══════════════════════════════════════════════════════════════

def show_allocation_detail(filter_fund=None):
    header("📊 자산배분 상세 (Allocation Detail)")
    fields = [
        ("equity_total",   "주식 합계"),
        ("public_equity",  "  ├ 상장주식"),
        ("private_equity", "  └ 사모주식"),
        ("fixed_income",   "채권/FI"),
        ("real_estate",    "부동산"),
        ("infrastructure", "인프라"),
        ("credit",         "크레딧"),
        ("alternatives",   "대체투자"),
        ("cash_other",     "현금/기타"),
    ]
    data = [r for r in ALLOCATION_DETAIL
            if filter_fund is None or filter_fund.lower() in r["fund"].lower()]
    if not data:
        print("  해당 펀드 없음"); return

    for row in data:
        sub_header(f"{row['fund']}  |  {row['year']}  |  AUM {row['aum']:,} {row['currency']}")
        print(f"  {'항목':<18} {'비중':>7}")
        print("  " + "-"*26)
        for key, label in fields:
            v = row.get(key)
            if v is not None:
                print(f"  {label:<18} {pct_plain(v):>7}")
        if row["notes"]:
            print(f"  ※ {row['notes']}")
    print()


def show_geographic_exposure(filter_fund=None):
    header("🌏 국가별 익스포져 (Geographic Exposure)")
    regions = [
        ("north_america", "북미 전체"),
        ("usa",           "  ├ 미국"),
        ("canada",        "  ├ 캐나다"),
        ("new_zealand",   "  └ 뉴질랜드"),
        ("europe",        "유럽"),
        ("asia_pacific",  "아시아태평양"),
        ("latin_america", "중남미"),
        ("australia",     "호주"),
        ("other",         "기타/EM"),
    ]
    data = [r for r in GEOGRAPHIC_EXPOSURE
            if filter_fund is None or filter_fund.lower() in r["fund"].lower()]
    if not data:
        print("  해당 펀드 없음"); return

    for row in data:
        sub_header(f"{row['fund']}  |  {row['year']}")
        print(f"  {'지역':<18} {'비중':>7}")
        print("  " + "-"*26)
        for key, label in regions:
            v = row.get(key)
            if v is not None:
                print(f"  {label:<18} {pct_plain(v):>7}")
        if row["notes"]:
            print(f"  ※ {row['notes']}")
    print()


def show_returns_by_asset_class(filter_fund=None):
    header("📈 Asset Class별 1년 수익률 (Returns by Asset Class)")
    fields = [
        ("total",          "총 펀드"),
        ("public_equity",  "상장주식"),
        ("private_equity", "사모주식"),
        ("fixed_income",   "채권/FI"),
        ("real_estate",    "부동산"),
        ("infrastructure", "인프라"),
        ("real_assets",    "실물자산 합계"),
        ("credit",         "크레딧"),
        ("alternatives",   "대체투자"),
    ]
    data = [r for r in RETURNS_BY_ASSET_CLASS
            if filter_fund is None or filter_fund.lower() in r["fund"].lower()]
    if not data:
        print("  해당 펀드 없음"); return

    for row in data:
        sub_header(f"{row['fund']}  |  {row['year']}")
        print(f"  {'항목':<16} {'수익률':>9}")
        print("  " + "-"*26)
        for key, label in fields:
            v = row.get(key)
            if v is not None:
                print(f"  {label:<16} {pct(v):>9}")
        if row["notes"]:
            print(f"  ※ {row['notes']}")
    print()


def show_multi_year_returns(filter_fund=None):
    header("📅 다년도 수익률 추이 (Multi-Year Returns)")
    data = [r for r in MULTI_YEAR_RETURNS
            if filter_fund is None or filter_fund.lower() in r["fund"].lower()]
    if not data:
        print("  해당 펀드 없음"); return

    fmt = "{:<34} {:>5}  {:>8}  {:>8}  {:>8}  {:>9}  {:>9}"
    print(fmt.format("펀드","통화","1년(최신)","1년(전년)","5년(연환)","10년(연환)","설정이후"))
    divider("-", 86)
    for r in data:
        print(fmt.format(
            r["fund"][:34], r["currency"],
            pct_plain(r["yr_1"]),
            pct_plain(r["yr_1_prior"]),
            pct_plain(r["yr_5"]),
            pct_plain(r["yr_10"]),
            pct_plain(r["since_inception"]),
        ))
    print()


def list_funds():
    funds = sorted(set(r["fund"] for r in ALLOCATION_DETAIL))
    print("\n  ── 수록 펀드 목록 ──")
    for i, f in enumerate(funds, 1):
        print(f"  {i:2}. {f}")
    print()


# ══════════════════════════════════════════════════════════════
# 4. 메인 메뉴
# ══════════════════════════════════════════════════════════════

MENU = """
╔══════════════════════════════════════════════════════════════╗
║        글로벌 연기금 / 국부펀드 투자 데이터 뷰어             ║
╠══════════════════════════════════════════════════════════════╣
║  1  자산배분 상세          (Allocation Detail)               ║
║  2  국가별 익스포져        (Geographic Exposure)             ║
║  3  Asset Class별 수익률   (Returns by Asset Class)          ║
║  4  다년도 수익률 추이     (Multi-Year Returns)              ║
║  5  전체 출력              (모든 시트 한번에)                ║
║  6  펀드 목록 보기                                           ║
║  q  종료                                                     ║
╚══════════════════════════════════════════════════════════════╝
"""

VIEW_MAP = {
    "1": show_allocation_detail,
    "2": show_geographic_exposure,
    "3": show_returns_by_asset_class,
    "4": show_multi_year_returns,
}

def ask_filter():
    val = input("  특정 펀드만 보려면 이름(일부) 입력, 전체는 엔터: ").strip()
    return val if val else None

def main():
    while True:
        print(MENU)
        choice = input("선택 (1-6 / q): ").strip().lower()
        if choice == "q":
            print("\n  bye!\n"); break
        elif choice in VIEW_MAP:
            f = ask_filter(); print()
            VIEW_MAP[choice](filter_fund=f)
            input("  [엔터] 메뉴로 돌아가기...")
        elif choice == "5":
            f = ask_filter(); print()
            show_allocation_detail(f)
            show_geographic_exposure(f)
            show_returns_by_asset_class(f)
            show_multi_year_returns(f)
            input("  [엔터] 메뉴로 돌아가기...")
        elif choice == "6":
            list_funds()
            input("  [엔터] 메뉴로 돌아가기...")
        else:
            print("  잘못된 입력입니다.\n")

if __name__ == "__main__":
    main()
