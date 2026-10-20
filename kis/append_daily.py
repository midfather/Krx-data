"""일봉 증분 추가·보정(2026-10-20): 일봉 파일(data/kis/daily/코드.csv)은 'daily' 수동 채우기 모드에서만 갱신돼 10/16에서 멈춰 있었다.
매 실행 끝에 호출된다.
1) 추가: 마지막 일봉 날짜 뒤의 날짜 폴더마다 15:30 이후 첫 스냅샷 값(시가·고가·저가·현재가·거래량·거래대금)을 한 줄로 붙인다. 일봉 파일이 없는 코드(지수 등)는 건너뛴다.
2) 보정(공식 종가 우선): 날짜 D의 공식 종가는 '다음 거래일 이후 폴더의 investor_코드.csv'에 있는 D 행의 stck_clpr이다.
   (실측: SK하이닉스 10/19는 당일 폴더 investor·스냅샷 모두 시간외 반영 1,285,000, 다음 날 폴더 investor는 정규장 종가 1,277,000.)
   최근 10개 폴더 안의 날짜에 대해 더 늦은 폴더의 공식 값이 있으면 종가를 그 값으로 고친다. 마지막 날짜는 다음 날 보정되기 전까지 잠정값이다.
멱등이며, 실패해도 수집이 깨지지 않게 fetch.py가 try/except로 감싼다.
"""
import os, csv

FIELDS = ["date", "open", "high", "low", "close", "vol", "amt"]


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []


def _official(base, folders, code):
    """날짜 -> 공식 종가. 더 늦은 폴더의 값이 우선(같은 날짜가 여러 폴더에 있으면 가장 늦은 폴더)."""
    out = {}
    for d in folders[-10:]:
        for iv in _rows(os.path.join(base, d, f"investor_{code}.csv")):
            dt, c = iv.get("stck_bsop_date"), iv.get("stck_clpr")
            if dt and c:
                out[dt] = c
    return out


def run(base="data/kis"):
    ddir = os.path.join(base, "daily")
    if not os.path.isdir(ddir):
        return 0, 0
    folders = sorted(d for d in os.listdir(base) if d.isdigit() and len(d) == 8)
    added = fixed = 0
    for fn in sorted(os.listdir(ddir)):
        if not fn.endswith(".csv"):
            continue
        code, path = fn[:-4], os.path.join(ddir, fn)
        rows = _rows(path)
        if not rows:
            continue
        last = max(r["date"] for r in rows)
        for d in folders:
            if d <= last:
                continue
            snap = [r for r in _rows(os.path.join(base, d, "snapshot.csv")) if r.get("code") == code and r.get("time", "") >= "1530"]
            if not snap:
                continue
            t0 = min(r["time"] for r in snap)
            r = next(x for x in snap if x["time"] == t0)
            try:
                rows.append({"date": d, "open": r["open"], "high": r["high"], "low": r["low"], "close": r["price"], "vol": r["vol"], "amt": r["amt"]})
                added += 1
            except KeyError:
                continue
        off = _official(base, folders, code)
        recent = set(folders[-10:])
        for r in rows:
            if r["date"] in recent and r["date"] in off and str(r["close"]) != str(off[r["date"]]):
                r["close"] = off[r["date"]]
                fixed += 1
        rows.sort(key=lambda r: r["date"])
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return added, fixed


if __name__ == "__main__":
    print("appended/fixed", run())
