# SEC XBRL companyfacts로 재무 요약(TTM 매출·성장, FCF, 희석, 총이익률, 현금·부채 등) — 공개 무료 API, 키 없음
# 입력: data/sec/list.txt(한 줄에 티커). 출력: data/sec/summary.csv, data/sec/_status.json
import json, csv, os, time, datetime, urllib.request, gzip, io
UA = {"User-Agent": "Krx-data research bot krx-bot@users.noreply.github.com", "Accept-Encoding": "gzip", "Host": None}
UA = {k: v for k, v in UA.items() if v}
def get(url):
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=60) as f:
        b = f.read()
        if f.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
    time.sleep(0.15); return json.loads(b)
os.makedirs("data/sec", exist_ok=True)
status = {"run_utc": datetime.datetime.utcnow().isoformat(), "ok": 0, "fail": []}
try:
    tick = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in get("https://www.sec.gov/files/company_tickers.json").values()}
except Exception as e:
    status["fatal"] = f"company_tickers: {type(e).__name__} {str(e)[:200]}"
    json.dump(status, open("data/sec/_status.json", "w"), indent=1); raise SystemExit(0)
D = lambda s: datetime.date.fromisoformat(s)
def facts(f, tags, unit="USD"):
    for tg in tags:
        x = f.get("us-gaap", {}).get(tg, {}).get("units", {}).get(unit)
        if x: return tg, x
    return None, []
def dur(e): return (D(e["end"]) - D(e["start"])).days if e.get("start") else None
def ttm(rows):
    """YTD 방식: 최신 기간(누적) + 직전 연간 − 전년 같은 누적. 반환 (TTM, 기준일, 전년 TTM)"""
    rows = [r for r in rows if r.get("start") and r.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")]
    if not rows: return None, None, None
    # 같은 (start,end)는 최신 신고값
    m = {}
    for r in sorted(rows, key=lambda r: r.get("filed", "")): m[(r["start"], r["end"])] = r["val"]
    items = [(D(s), D(e), v) for (s, e), v in m.items()]
    def calc(asof):
        cand = [(s, e, v) for s, e, v in items if e <= asof]
        if not cand: return None, None
        e_last = max(e for _, e, _ in cand)
        ytd = [(s, e, v) for s, e, v in cand if e == e_last]
        s0, e0, v0 = min(ytd, key=lambda t: t[0])  # 가장 긴 누적
        d0 = (e0 - s0).days
        if 350 <= d0 <= 380: return v0, e0
        fy = [(s, e, v) for s, e, v in items if 350 <= (e - s).days <= 380 and abs((e - s0).days) <= 5]
        prev = [(s, e, v) for s, e, v in items if abs((e - e0).days - 365) <= 10 and abs(((e - s).days) - d0) <= 10]
        if fy and prev:
            return fy[0][2] + v0 - prev[0][2], e0
        return None, e0
    cur, e0 = calc(datetime.date.today())
    if e0 is None: return None, None, None
    prv, _ = calc(e0 - datetime.timedelta(days=360))
    return cur, e0, prv
def instant(f, tags, ns="us-gaap", unit="USD"):
    for tg in tags:
        x = f.get(ns, {}).get(tg, {}).get("units", {}).get(unit)
        if x:
            x = sorted(x, key=lambda r: (r["end"], r.get("filed", "")))
            return x
    return []
out = []
for t in [l.strip().upper() for l in open("data/sec/list.txt") if l.strip()]:
    row = {"sym": t}
    try:
        cik = tick.get(t.replace(".", "-")) or tick.get(t)
        if not cik: row["err"] = "no cik"; out.append(row); continue
        f = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")["facts"]
        _, rv = facts(f, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"])
        rev, end, rev_p = ttm(rv); row.update(rev=rev, rev_prev=rev_p, asof=str(end))
        _, gp = facts(f, ["GrossProfit"]); g, _, g_p = ttm(gp); row.update(gp=g, gp_prev=g_p)
        _, oi = facts(f, ["OperatingIncomeLoss"]); o, _, o_p = ttm(oi); row.update(opinc=o, opinc_prev=o_p)
        _, ni = facts(f, ["NetIncomeLoss"]); n, _, _ = ttm(ni); row.update(ni=n)
        _, ocf = facts(f, ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]); oc, _, oc_p = ttm(ocf)
        _, cx = facts(f, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]); c, _, c_p = ttm(cx)
        row.update(ocf=oc, capex=c, fcf=(oc - (c or 0)) if oc is not None else None, fcf_prev=(oc_p - (c_p or 0)) if oc_p is not None else None)
        _, da = facts(f, ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"]); d, _, _ = ttm(da); row.update(da=d)
        sh = instant(f, ["EntityCommonStockSharesOutstanding"], ns="dei", unit="shares")
        if sh:
            byd = {}
            for r in sh: byd.setdefault(r["end"], {})[r.get("frame") or r.get("accn")] = r["val"]
            dates = sorted(byd); last = dates[-1]; s_now = sum(byd[last].values())
            old = [d_ for d_ in dates if 330 <= (D(last) - D(d_)).days <= 430]
            s_old = sum(byd[old[-1]].values()) if old else None
            row.update(shares=s_now, shares_1y=s_old, shares_date=last)
        cash = instant(f, ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"])
        row["cash"] = cash[-1]["val"] if cash else None
        debt_tags = [["LongTermDebt"], ["LongTermDebtNoncurrent"], ["LongTermDebtCurrent"], ["ConvertibleNotesPayable", "ConvertibleDebtNoncurrent"], ["OperatingLeaseLiabilityNoncurrent"]]
        lt = instant(f, ["LongTermDebt"]); ltn = instant(f, ["LongTermDebtNoncurrent"]); ltc = instant(f, ["LongTermDebtCurrent"])
        row["debt"] = lt[-1]["val"] if lt else ((ltn[-1]["val"] if ltn else 0) + (ltc[-1]["val"] if ltc else 0)) or None
        ta = instant(f, ["Assets"])
        if ta:
            row["assets"] = ta[-1]["val"]; a_old = [r for r in ta if 330 <= (D(ta[-1]["end"]) - D(r["end"])).days <= 430]
            row["assets_1y"] = a_old[-1]["val"] if a_old else None
        status["ok"] += 1
    except Exception as e:
        row["err"] = str(e)[:120]; status["fail"].append(t)
    out.append(row)
keys = sorted({k for r in out for k in r}, key=lambda k: (k != "sym", k))
with open("data/sec/summary.csv", "w", newline="") as fo:
    w = csv.DictWriter(fo, fieldnames=keys); w.writeheader(); w.writerows(out)
json.dump(status, open("data/sec/_status.json", "w"), indent=1)
print(status["ok"], len(status["fail"]))
