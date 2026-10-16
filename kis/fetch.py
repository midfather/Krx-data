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
log["ok"] = sum(c["ok"] for c in log["calls"]); log["fail"] = sum(not c["ok"] for c in log["calls"])
json.dump(log, open("data/kis/_status.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", log["ok"], "fail", log["fail"])
