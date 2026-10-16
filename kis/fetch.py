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
    log["calls"].append({"path": path, "tr": tr, "code": (params or {}).get("FID_INPUT_ISCD"), "ok": ok,
                         "msg": js.get("msg1") or js.get("err") or js.get("error_description")})
    time.sleep(0.12)  # 초당 호출 제한(실전 20건/초) 여유
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
                         "amt": o.get("acml_tr_pbmn"), "frgn_net": o.get("frgn_ntby_qty"), "pgm_net": o.get("pgtr_ntby_qty")})
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
        ks = ["time", "code", "name", "price", "chg", "chg_pct", "open", "high", "low", "vol", "amt", "frgn_net", "pgm_net"]
        with open(fn, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ks, extrasaction="ignore")
            if new: w.writeheader()
            w.writerows(snap)
        json.dump(snap, open("data/kis/latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
log["ok"] = sum(c["ok"] for c in log["calls"]); log["fail"] = sum(not c["ok"] for c in log["calls"])
json.dump(log, open("data/kis/_status.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok", log["ok"], "fail", log["fail"])
