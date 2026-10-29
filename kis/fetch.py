# 한국투자증권 Open API — 장중 시세·분봉·투자자 수급 수집 (조회 전용, 주문 기능 없음)
# 키는 GitHub Secrets(KIS_APP_KEY, KIS_APP_SECRET)에서만 읽는다. 키·토큰은 파일에 쓰지 않는다.
import os, json, csv, time, datetime, urllib.request, urllib.error
BASE = "https://openapi.koreainvestment.com:9443"
KEY, SEC = os.environ["KIS_APP_KEY"].strip(), os.environ["KIS_APP_SECRET"].strip()
CODES = {"102110": "TIGER 200", "0183J0": "TIGER 미국우주테크", "0195S0": "TIGER SK하이닉스단일",
         "442580": "PLUS 글로벌HBM반도체", "487240": "KODEX AI전력핵심설비", "147970": "TIGER 모멘텀",
         "496080": "TIGER 코리아밸류업", "005930": "삼성전자", "000660": "SK하이닉스"}
IDX = {"0001": "코스피", "2001": "코스피200"}
kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
D, T = kst.strftime("%Y%m%d"), kst.strftime("%H%M")
OUT = f"data/kis/{D}"; os.makedirs(OUT, exist_ok=True)
log = {"run_kst": kst.strftime("%Y-%m-%d %H:%M"), "calls": []}

params_retry = {}
def req(method, path, tr=None, params=None, body=None, tok=None):
    url = BASE + path + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
    h = {"content-type": "application/json; charset=utf-8", "appkey": KEY, "appsecret": SEC, "custtype": "P"}
    if tok: h["authorization"] = "Bearer " + tok
    if tr: h["tr_id"] = tr
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as f: js = json.loads(f.read().decode("utf-8"))
        ok = js.get("rt_cd", "0") == "0"
    except urllib.error.HTTPError as e:
        js = {"http": e.code, "err": e.read().decode("utf-8", "ignore")[:200]}; ok = False
    except Exception as e:
        js = {"err": str(e)[:200]}; ok = False
    if not ok and "EGW00201" in json.dumps(js, ensure_ascii=False) and not params_retry.get(path + str(params)):
        params_retry[path + str(params)] = 1; time.sleep(1.1); return req(method, path, tr, params, body, tok)
    log["calls"].append({"path": path, "tr": tr, "code": (params or {}).get("FID_INPUT_ISCD"), "ok": ok,
                         "msg": js.get("msg1") or js.get("err") or js.get("error_description")})
    time.sleep(0.35)  # 초당 호출 제한 여유(신규 계좌는 제한이 낮음) — 초과(EGW00201) 시 1초 뒤 1회 재시도
    return js if ok else None

t = req("POST", "/oauth2/tokenP", body={"grant_type": "client_credentials", "appkey": KEY, "appsecret": SEC})
tok = t and t.get("access_token")
if tok:
    snap = []
    for c, n in CODES.items():
        p = req("GET", "/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": c}, tok=tok)
        if p:
            o = p["output"]
            snap.append({"time": T, "code": c, "name": n, "price": o.get("stck_prpr"), "chg": o.get("prdy_vrss"), "chg_pct": o.get("prdy_ctrt"),
                         "open": o.get("stck_oprc"), "high": o.get("stck_hgpr"), "low": o.get("stck_lwpr"), "vol": o.get("acml_vol"),
                         "amt": o.get("acml_tr_pbmn"), "frgn_net": o.get("frgn_ntby_qty"), "pgm_net": o.get("pgtr_ntby_qty"), "per": o.get("per"), "pbr": o.get("pbr"), "eps": o.get("eps"), "w52_hi": o.get("w52_hgpr"), "w52_lo": o.get("w52_lwpr")})
        m = req("GET", "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice", "FHKST03010200",
                {"FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": c, "FID_INPUT_HOUR_1": kst.strftime("%H%M%S"), "FID_PW_DATA_INCU_YN": "Y"}, tok=tok)
        if m and m.get("output2"):
            fn = f"{OUT}/min_{c}.csv"; old = {}
            if os.path.exists(fn):
                for r in csv.DictReader(open(fn, encoding="utf-8")): old[r["hhmmss"]] = r
            for b in m["output2"]:
                if b.get("stck_bsop_date") == D:
                    old[b["stck_cntg_hour"]] = {"hhmmss": b["stck_cntg_hour"], "open": b["stck_oprc"], "high": b["stck_hgpr"], "low": b["stck_lwpr"], "close": b["stck_prpr"], "vol": b["cntg_vol"]}
            if old:
                with open(fn, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["hhmmss", "open", "high", "low", "close", "vol"]); w.writeheader()
                    for k in sorted(old): w.writerow(old[k])
        v = req("GET", "/uapi/domestic-stock/v1/quotations/inquire-investor", "FHKST01010900", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": c}, tok=tok)
        if v and v.get("output"):
            rows = v["output"][:20]
            with open(f"{OUT}/investor_{c}.csv", "w", newline="", encoding="utf-8") as f:
                ks = ["stck_bsop_date", "stck_clpr", "prsn_ntby_qty", "frgn_ntby_qty", "orgn_ntby_qty", "prsn_ntby_tr_pbmn", "frgn_ntby_tr_pbmn", "orgn_ntby_tr_pbmn"]
                w = csv.DictWriter(f, fieldnames=ks, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    for c, n in IDX.items():
        p = req("GET", "/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100000", {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": c}, tok=tok)
        if p:
            o = p["output"]
            snap.append({"time": T, "code": c, "name": n, "price": o.get("bstp_nmix_prpr"), "chg": o.get("bstp_nmix_prdy_vrss"), "chg_pct": o.get("bstp_nmix_prdy_ctrt"),
                         "open": o.get("bstp_nmix_oprc"), "high": o.get("bstp_nmix_hgpr"), "low": o.get("bstp_nmix_lwpr"), "vol": o.get("acml_vol"), "amt": o.get("acml_tr_pbmn")})
    if snap:
        fn = f"{OUT}/snapshot.csv"; new = not os.path.exists(fn)
        ks = ["time", "code", "name", "price", "chg", "chg_pct", "open", "high", "low", "vol", "amt", "frgn_net", "pgm_net", "per", "pbr", "eps", "w52_hi", "w52_lo"]
        with open(fn, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ks, extrasaction="ignore")
            if new: w.writeheader()
            w.writerows(snap)
        json.dump(snap, open("data/kis/latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 해외 보유 종목 현재가(2026-10-22) — 메리츠 장애 시 2순위 대안. 가격만 저장(수량·계좌 없음)
US_SYMS = {"NVDA": "NAS", "GOOGL": "NAS", "MSFT": "NAS", "JNJ": "NYS", "KO": "NYS", "QQQM": "NAS", "SPYM": "AMS", "IEF": "NAS",
           "RDW": "NYS", "IREN": "NAS", "ARKF": "AMS", "XRPI": "NAS", "AMZN": "NAS", "UNH": "NYS", "O": "NYS", "QLD": "AMS",
           "QQQI": "NAS", "SGOV": "NYS", "SPMO": "AMS"}
if tok:
    usnap = []
    for s_, ex_ in US_SYMS.items():
        r_ = req("GET", "/uapi/overseas-price/v1/quotations/price", "HHDFS00000300", {"AUTH": "", "EXCD": ex_, "SYMB": s_}, tok=tok)
        o_ = (r_ or {}).get("output") or {}
        if o_.get("last") not in (None, "", "0", "0.0000"):
            usnap.append({"symbol": s_, "price": o_.get("last"), "chg_pct": o_.get("rate"), "base": o_.get("base"), "time_kst": kst.strftime("%Y-%m-%d %H:%M")})
    if usnap:
        os.makedirs("data/kis", exist_ok=True)
        json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "prices": usnap}, open("data/kis/us_latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 미국 주요 지수 일봉(2026-10-28) — 한투 '해외주식 종목/지수/환율기간별시세'(FHKST03030100, 시장구분 N). QQQ 대용 아님, 지수 자체.
# 지수 코드는 공식 문서에 명시가 없어 후보를 차례로 시험하고, 되는 코드와 실패 사유(비밀값 없음)를 data/kis/us_index_probe.json에 남긴다.
US_INDEX = {"NDX": ["NDX", ".NDX", "NDX100"], "SPX": ["SPX", ".SPX", "GSPC"], "IXIC": ["COMP", ".IXIC", "IXIC"], "SOX": ["SOX", ".SOX"]}
if tok:
    try:
        os.makedirs("data/kis/us_index", exist_ok=True); probe = {}; ilatest = {}
        for nm, cands in US_INDEX.items():
            fn = f"data/kis/us_index/{nm}.csv"; rows = {}
            if os.path.exists(fn):
                for r_ in csv.DictReader(open(fn, encoding="utf-8")): rows[r_["date"]] = r_
            pages = 6 if len(rows) < 260 else 1   # 200일선 계산용으로 처음엔 약 500일 채움
            for cd in cands:
                end = kst; got = {}; msg = ""
                for _ in range(pages):
                    st = end - datetime.timedelta(days=140)
                    d_ = req("GET", "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice", "FHKST03030100",
                             {"FID_COND_MRKT_DIV_CODE": "N", "FID_INPUT_ISCD": cd, "FID_INPUT_DATE_1": st.strftime("%Y%m%d"), "FID_INPUT_DATE_2": end.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D"}, tok=tok)
                    if not d_: break
                    for b in d_.get("output2", []) or []:
                        if b.get("stck_bsop_date") and b.get("ovrs_nmix_prpr") not in (None, "", "0", "0.0000"):
                            got[b["stck_bsop_date"]] = {"date": b["stck_bsop_date"], "open": b.get("ovrs_nmix_oprc"), "high": b.get("ovrs_nmix_hgpr"), "low": b.get("ovrs_nmix_lwpr"), "close": b["ovrs_nmix_prpr"], "vol": b.get("acml_vol")}
                    o1 = d_.get("output1") or {}
                    if o1 and "info" not in ilatest.get(nm, {}): ilatest[nm] = {"code": cd, "price": o1.get("ovrs_nmix_prpr"), "chg": o1.get("ovrs_nmix_prdy_vrss"), "chg_pct": o1.get("prdy_ctrt"), "prev_close": o1.get("ovrs_nmix_prdy_clpr"), "time_kst": kst.strftime("%Y-%m-%d %H:%M")}
                    end = st - datetime.timedelta(days=1)
                probe[nm] = {"code": cd, "rows": len(got), "ok": bool(got)}
                if got:
                    rows.update(got); break
            if rows:
                with open(fn, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "vol"], extrasaction="ignore"); w.writeheader()
                    for k in sorted(rows): w.writerow(rows[k])
        json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "probe": probe}, open("data/kis/us_index_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if ilatest: json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "indices": ilatest}, open("data/kis/us_index_latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e_:
        json.dump({"error": type(e_).__name__ + ": " + str(e_)[:150]}, open("data/kis/us_index_probe.json", "w", encoding="utf-8"))

# 미국 지수선물(E-mini S&P500 ES, E-mini 나스닥100 NQ) 현재가 — 한투 '해외선물옵션 종목현재가'(HHDFC55010000). 만기월 후보를 차례로 시험하고 결과를 data/kis/us_futures_probe.json에 남긴다(비밀값 없음).
if tok:
    try:
        fprobe = {}; flatest = {}
        for nm, roots in {"ES": ["ESZ26", "ESH27"], "NQ": ["NQZ26", "NQH27"]}.items():
            for cd in roots:
                d_ = req("GET", "/uapi/overseas-futureoption/v1/quotations/inquire-price", "HHDFC55010000", {"SRS_CD": cd}, tok=tok)
                o_ = (d_ or {}).get("output1") or (d_ or {}).get("output") or {}
                fprobe[cd] = {"ok": bool(o_), "keys": sorted(o_.keys())[:40] if isinstance(o_, dict) else []}
                if o_ and nm not in flatest:
                    flatest[nm] = {"code": cd, "raw": o_, "time_kst": kst.strftime("%Y-%m-%d %H:%M")}
                    break
        json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "probe": fprobe}, open("data/kis/us_futures_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if flatest: json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "futures": flatest}, open("data/kis/us_futures_latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e_:
        json.dump({"error": type(e_).__name__ + ": " + str(e_)[:150]}, open("data/kis/us_futures_probe.json", "w", encoding="utf-8"))

# 선물 대체 경로 시험(2026-10-29): 해외지수 기간별시세 TR에 시장구분·선물 코드 후보를 넣어 본다. 결과(코드·행수·메시지, 비밀값 없음)만 data/kis/us_fut_probe2.json에 저장.
if tok and "us-fut2" in (open(".github/triggers/kis.txt", encoding="utf-8").read() if os.path.exists(".github/triggers/kis.txt") else ""):
    try:
        pr2 = {}
        for dv in ["N", "F", "S"]:
            for cd in ["ES", "NQ", "ESZ26", "NQZ26", "ES1!", "NQ1!", "ES=F", "NQ=F", "SPXFUT", "NDXFUT"]:
                st = kst - datetime.timedelta(days=10)
                d_ = req("GET", "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice", "FHKST03030100",
                         {"FID_COND_MRKT_DIV_CODE": dv, "FID_INPUT_ISCD": cd, "FID_INPUT_DATE_1": st.strftime("%Y%m%d"), "FID_INPUT_DATE_2": kst.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D"}, tok=tok)
                n = len((d_ or {}).get("output2", []) or [])
                pr2[f"{dv}:{cd}"] = {"rows": n, "price": ((d_ or {}).get("output1") or {}).get("ovrs_nmix_prpr")}
        json.dump({"time_kst": kst.strftime("%Y-%m-%d %H:%M"), "probe": pr2}, open("data/kis/us_fut_probe2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e_:
        json.dump({"error": type(e_).__name__ + ": " + str(e_)[:150]}, open("data/kis/us_fut_probe2.json", "w", encoding="utf-8"))

# 일봉 채우기 모드: .github/triggers/kis.txt 내용에 'daily'가 있으면 종목별 일봉 약 400일을 data/kis/daily/코드.csv로 저장(덮어씀)
MODE = open(".github/triggers/kis.txt", encoding="utf-8").read() if os.path.exists(".github/triggers/kis.txt") else ""
if tok and "daily" in MODE:
    os.makedirs("data/kis/daily", exist_ok=True)
    for c in CODES:
        rows = {}; end = kst
        for _ in range(5):
            st = end - datetime.timedelta(days=140)
            d = req("GET", "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100",
                    {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": c, "FID_INPUT_DATE_1": st.strftime("%Y%m%d"), "FID_INPUT_DATE_2": end.strftime("%Y%m%d"), "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"}, tok=tok)
            for b in (d or {}).get("output2", []) or []:
                if b.get("stck_bsop_date"):
                    rows[b["stck_bsop_date"]] = {"date": b["stck_bsop_date"], "open": b["stck_oprc"], "high": b["stck_hgpr"], "low": b["stck_lwpr"], "close": b["stck_clpr"], "vol": b["acml_vol"], "amt": b["acml_tr_pbmn"]}
            end = st - datetime.timedelta(days=1)
        if rows:
            with open(f"data/kis/daily/{c}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "vol", "amt"]); w.writeheader()
                for k in sorted(rows): w.writerow(rows[k])

# 미국 일봉 모드: kis.txt에 'us:AAA,BBB,...'가 있으면 종목별 일봉 약 300거래일 + 상세(시총·PER·상장주수)를 data/kis/us/에 저장
if tok and ("us:" in MODE or "uslong:" in MODE):
    PAGES = 16 if "uslong:" in MODE else 3
    key = "uslong:" if "uslong:" in MODE else "us:"
    syms = [s.strip().upper() for s in MODE.split(key, 1)[1].split()[0].split(",") if s.strip()]
    os.makedirs("data/kis/us", exist_ok=True); detail = {}
    for s in syms:
        got = False
        for ex in ("NAS", "NYS", "AMS", "BAY", "BAQ", "BAA"):
            rows = {}; bymd = ""
            for _ in range(PAGES):
                d = req("GET", "/uapi/overseas-price/v1/quotations/dailyprice", "HHDFS76240000",
                        {"AUTH": "", "EXCD": ex, "SYMB": s, "GUBN": "0", "BYMD": bymd, "MODP": "1"}, tok=tok)
                out = [b for b in ((d or {}).get("output2") or []) if b.get("xymd")]
                if not out: break
                for b in out:
                    rows[b["xymd"]] = {"date": b["xymd"], "open": b.get("open"), "high": b.get("high"), "low": b.get("low"), "close": b.get("clos"), "vol": b.get("tvol"), "amt": b.get("tamt")}
                oldest = min(b["xymd"] for b in out)
                bymd = (datetime.datetime.strptime(oldest, "%Y%m%d") - datetime.timedelta(days=1)).strftime("%Y%m%d")
            if rows:
                with open(f"data/kis/us/{s}.csv", "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "vol", "amt"]); w.writeheader()
                    for k in sorted(rows): w.writerow(rows[k])
                dt = req("GET", "/uapi/overseas-price/v1/quotations/price-detail", "HHDFS76200200", {"AUTH": "", "EXCD": ex, "SYMB": s}, tok=tok)
                o = (dt or {}).get("output") or {}
                detail[s] = {"excd": ex, "n": len(rows), "last": max(rows), "mcap": o.get("tomv"), "shares": o.get("shar"), "per": o.get("perx"), "pbr": o.get("pbrx"), "eps": o.get("epsx"), "h52": o.get("h52p"), "l52": o.get("l52p"), "cur": o.get("last")}
                got = True; break
        if not got: detail[s] = {"error": "no data on NAS/NYS/AMS/BAY/BAQ/BAA"}
    old = json.load(open("data/kis/us/_detail.json", encoding="utf-8")) if os.path.exists("data/kis/us/_detail.json") else {}
    old.update(detail); detail = old
    json.dump(detail, open("data/kis/us/_detail.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 조건검색 모드: kis.txt에 'screen:'이 있으면 해외주식 조건검색(HHDFS76410000, 한 번에 최대 100행·가격 내림차순)을
# 가격 구간을 나눠 가며 전부 받아 data/kis/us/universe.csv로 저장(시가총액 10억~150억 달러, 주가 ≥ 5달러, 나스닥·뉴욕)
if tok and "screen:" in MODE:
    LARGE = "screen:large" in MODE
    VLO, VHI = ("15000000", "9000000000") if LARGE else ("1000000", "15000000")
    os.makedirs("data/kis/us", exist_ok=True); rows = {}; meta = []
    def search(ex, lo, hi):
        prm = {"AUTH": "", "EXCD": ex, "CO_YN_PRICECUR": "1", "CO_ST_PRICECUR": f"{lo:.2f}", "CO_EN_PRICECUR": f"{hi:.2f}",
               "CO_YN_RATE": "", "CO_ST_RATE": "", "CO_EN_RATE": "", "CO_YN_VALX": "1", "CO_ST_VALX": VLO, "CO_EN_VALX": VHI,
               "CO_YN_SHAR": "", "CO_ST_SHAR": "", "CO_EN_SHAR": "", "CO_YN_VOLUME": "", "CO_ST_VOLUME": "", "CO_EN_VOLUME": "",
               "CO_YN_AMT": "", "CO_ST_AMT": "", "CO_EN_AMT": "", "CO_YN_EPS": "", "CO_ST_EPS": "", "CO_EN_EPS": "",
               "CO_YN_PER": "", "CO_ST_PER": "", "CO_EN_PER": "", "KEYB": ""}
        d = req("GET", "/uapi/overseas-price/v1/quotations/inquire-search", "HHDFS76410000", prm, tok=tok) or {}
        o1 = d.get("output1") or {}; o2 = d.get("output2") or []
        trec = int(o1.get("trec") or 0); crec = int(o1.get("crec") or 0)
        meta.append({"ex": ex, "lo": lo, "hi": hi, "trec": trec, "crec": crec})
        if trec > crec and hi - lo > 0.02:
            mid = round((lo + hi) / 2, 2); search(ex, lo, mid); search(ex, mid + 0.01, hi)
        else:
            for r in o2: rows[r["excd"] + ":" + r["symb"]] = r
    for ex in ("NAS", "NYS"):
        for lo, hi in ((5, 20), (20.01, 50), (50.01, 120), (120.01, 100000)):
            search(ex, lo, hi)
    keys = ["excd", "symb", "name", "ename", "last", "rate", "tvol", "avol", "valx", "shar", "eps", "per"]
    with open("data/kis/us/universe_large.csv" if LARGE else "data/kis/us/universe.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(rows.values())
    json.dump(meta, open("data/kis/us/universe_meta_large.json" if LARGE else "data/kis/us/universe_meta.json", "w"), indent=0)

# 대량 일봉 모드: kis.txt에 'bulk:'가 있으면 data/kis/us/bulk_list.txt(한 줄에 EXCD:SYMB)의 종목별 일봉 300거래일을 data/kis/us/bulk/SYMB.csv로
def _bulk_one(ex, s, fn):
    rows = {}; bymd = ""
    for _ in range(3):
        d = req("GET", "/uapi/overseas-price/v1/quotations/dailyprice", "HHDFS76240000", {"AUTH": "", "EXCD": ex, "SYMB": s, "GUBN": "0", "BYMD": bymd, "MODP": "1"}, tok=tok)
        out = [b for b in ((d or {}).get("output2") or []) if b.get("xymd")]
        if not out: break
        for b in out: rows[b["xymd"]] = (b["xymd"], b.get("open"), b.get("high"), b.get("low"), b.get("clos"), b.get("tvol"), b.get("tamt"))
        bymd = (datetime.datetime.strptime(min(b["xymd"] for b in out), "%Y%m%d") - datetime.timedelta(days=1)).strftime("%Y%m%d")
    if rows:
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["date", "open", "high", "low", "close", "vol", "amt"])
            for k in sorted(rows): w.writerow(rows[k])
bulk_err = []
if tok and "bulk:" in MODE and os.path.exists("data/kis/us/bulk_list.txt"):
    os.makedirs("data/kis/us/bulk", exist_ok=True)
    for line in open("data/kis/us/bulk_list.txt", encoding="utf-8"):
        line = line.strip()
        if ":" not in line: continue
        ex, s = line.split(":", 1); fn = f"data/kis/us/bulk/{s.replace('/', '_')}.csv"
        if os.path.exists(fn): continue
        try:
            _bulk_one(ex, s, fn)
        except Exception as e:
            bulk_err.append(f"{s}: {type(e).__name__} {str(e)[:80]}")
    log["bulk_err"] = bulk_err[:50]
    log["calls"] = [c for c in log["calls"] if not c["ok"]][:200] + [{"path": "bulk", "ok": True, "msg": f"{len(os.listdir('data/kis/us/bulk'))} files"}]
log["ok"] = sum(c["ok"] for c in log["calls"]); log["fail"] = sum(not c["ok"] for c in log["calls"])
json.dump(log, open("data/kis/_status.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", log["ok"], "fail", log["fail"])

# 일봉 증분 추가·보정(2026-10-20) — 실패해도 수집 결과에 영향 없음
try:
    import append_daily
    print("append_daily", append_daily.run())
except Exception as e:
    print("append_daily 실패:", type(e).__name__, str(e)[:120])
