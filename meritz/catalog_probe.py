#!/usr/bin/env python3
"""메리츠 공식 조회 카탈로그의 항목 이름·설명만 data/meritz/catalog_keys.json 으로 저장(비밀값·계좌 없음)."""
import json, os
os.environ["MERITZ_READ_ONLY"] = "1"
from meritz import load_catalog
cat = load_catalog()
out = {"type": type(cat).__name__}
def short(v):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s[:300]
items = {}
try:
    src = cat if isinstance(cat, dict) else (vars(cat) if hasattr(cat, "__dict__") else {})
    for k, v in src.items():
        items[str(k)] = short(v)
except Exception as e:
    out["iter_error"] = type(e).__name__
out["attrs"] = [a for a in dir(cat) if not a.startswith("_")][:60]
out["items"] = items
for k in ("keys", "names", "list", "all"):
    f = getattr(cat, k, None)
    if callable(f):
        try: out[k] = [str(x) for x in list(f())][:400]
        except Exception as e: out[k + "_error"] = type(e).__name__
os.makedirs("data/meritz", exist_ok=True)
json.dump(out, open("data/meritz/catalog_keys.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
