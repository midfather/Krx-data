#!/usr/bin/env python3
"""메리츠 Open API 현재가만 data/meritz/latest.json 으로 내보낸다. 수량·잔고·계좌 정보는 다루지 않는다."""
import datetime as dt, json, os, sys
os.environ["MERITZ_READ_ONLY"] = "1"
KST = dt.timezone(dt.timedelta(hours=9))
here = os.path.dirname(os.path.abspath(__file__))
wl = json.load(open(os.path.join(here, "watchlist.json"), encoding="utf-8"))
from meritz import client, load_catalog
cat, c = load_catalog(), client()
def f(x):
    try: return float(x)
    except Exception: return None
us, kr, errors = [], [], []
us_t = kr_t = None
for it in wl["us"]:
    try:
        r = c.call(cat.get("ovs_market_prices"), {"mrkt_div_code": "OV", "mrkt_cls_code": it["exch"], "iscd": it["symbol"], "dely_rltm_cls_code": "0"})
        d = r.get("body", {}).get("data") if r.get("ok") else None
        if not d or not f(d.get("prpr")):
            errors.append({"symbol": it["symbol"], "error": "empty"}); continue
        us.append({"symbol": it["symbol"], "name": it["name"], "price": f(d["prpr"]), "change": f(d.get("prdy_vrss")), "change_pct": f(d.get("prdy_ctrt")), "prev_close": f(d.get("prdy_clpr"))})
    except Exception as e:
        errors.append({"symbol": it["symbol"], "error": type(e).__name__})
us_t = dt.datetime.now(KST).isoformat(timespec="seconds")
for it in wl["kr"]:
    try:
        r = c.call(cat.get("market_prices"), {"mrkt_div_code": "J", "iscd": it["code"]})
        d = r.get("body", {}).get("data") if r.get("ok") else None
        if not d or not f(d.get("stck_prpr")):
            errors.append({"code": it["code"], "error": "empty"}); continue
        kr.append({"code": it["code"], "name": it["name"], "price": int(f(d["stck_prpr"])), "change": int(f(d.get("prdy_vrss") or 0)), "change_pct": f(d.get("prdy_ctrt"))})
    except Exception as e:
        errors.append({"code": it["code"], "error": type(e).__name__})
kr_t = dt.datetime.now(KST).isoformat(timespec="seconds")
out = {"source": "meritz-open-api", "us_asof_kst": us_t, "kr_asof_kst": kr_t, "us": us, "kr": kr, "errors": errors}
text = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
for k in ("MERITZ_APP_KEY", "MERITZ_APP_SECRET", "MERITZ_ACCOUNT_NO"):
    v = os.environ.get(k, "")
    if len(v) >= 4 and v in text:
        print("중단: 비밀값 포함", file=sys.stderr); sys.exit(3)
if not us and not kr:
    print("중단: 조회 결과 없음", file=sys.stderr); sys.exit(4)
os.makedirs("data/meritz", exist_ok=True)
open("data/meritz/latest.json", "w", encoding="utf-8").write(text)
print(f"ok us={len(us)} kr={len(kr)} err={len(errors)}")
