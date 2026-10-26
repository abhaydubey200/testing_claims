"""End-to-end run: load -> download -> read photos -> checks -> Excel report."""
import os, json, shutil, tempfile, time, hashlib, concurrent.futures as cf
from datetime import datetime
import pandas as pd
from . import config as C, __version__
from .loader import load_claims
from .downloader import download_all, safe_name
from .analyzer import analyze_photo
from .checks import run_checks
from .report import write_report, check_priorities


def _code_stamp() -> str:
    """Fingerprint of the photo-reading code, mixed into the per-photo cache key.

    The cache is keyed by file size, name and claim date, so after a check or threshold was
    tuned a re-run happily replayed the *old* verdicts for every photo already seen - the fix
    looked like it did nothing. Hashing the reading code means a change invalidates it.
    """
    h = hashlib.md5()
    for name in ("analyzer.py", "textparse.py", "sparkle.py", "config.py"):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()[:8]


_CODE_STAMP = _code_stamp()


def run(input_path: str, out_dir: str, progress=None) -> dict:
    """progress(stage:str, done:int, total:int) is called as work proceeds. Returns a dict with the output path and counts."""
    t0 = time.time(); say = progress or (lambda *a: None)
    base = os.path.splitext(os.path.basename(input_path))[0]
    photo_dir = os.path.join(out_dir, base + "_photos"); os.makedirs(photo_dir, exist_ok=True)
    cache_path = os.path.join(photo_dir, "_analysis_cache.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}

    say("Reading claim file", 0, 1)
    _, odo = load_claims(input_path)
    if odo.empty:
        raise ValueError("No rows with odometer photo links were found in this file.")
    g = lambda r, c: r.get(c, "") if isinstance(r.get(c, ""), str) else ""
    claims = pd.DataFrame({
        "claim_key": odo["_row"].astype(int), "emp": odo[C.COL_EMP], "name": odo[C.COL_NAME], "zone": odo.get("Zone", ""),
        "hq": odo.get("HQ", ""), "designation": odo.get("Designation", ""), "l1": odo.get(C.COL_L1, ""),
        "claim_id": odo[C.COL_CLAIM], "claim_date": odo["_date"], "submit_date": odo["_submit"],
        "amount": odo[C.COL_AMOUNT + "_num"], "vehicle": odo.get("Vehicle Type", "")})
    claims = claims.fillna({"zone": "", "hq": "", "designation": "", "l1": "", "vehicle": ""})
    km = pd.to_numeric(odo.get(C.COL_KM, pd.Series([None] * len(odo))), errors="coerce")
    if km.notna().any():
        claims["km_claimed"] = km.values
    elif C.RATE_PER_KM:
        claims["km_claimed"] = [a / C.RATE_PER_KM[v] if C.RATE_PER_KM.get(v) else None for a, v in zip(claims.amount, claims.vehicle)]
    else:
        claims["km_claimed"] = None
    claims = claims.sort_values(["emp", "claim_date", "claim_id", "claim_key"]).reset_index(drop=True)

    # one row per photo
    rows = []
    for c in claims.itertuples():
        src = odo[odo["_row"] == c.claim_key].iloc[0]
        for side, col in (("START", C.COL_START), ("END", C.COL_END)):
            url = src[col]
            if not url: continue
            ext = os.path.splitext(url.split("?")[0])[1].lower() or ".jpg"
            rows.append({**c._asdict(), "side": side, "url": url,
                         "file": safe_name(f"{c.emp}_{c.claim_id}_R{c.claim_key}_{side}") + ext})
    P = pd.DataFrame(rows).drop(columns=["Index"], errors="ignore")
    P.insert(0, "pid", range(1, len(P) + 1))

    # download
    jobs = [(r.pid, r.url, r.file) for r in P.itertuples()]
    dl = download_all(jobs, photo_dir, progress=lambda d, n: say("Downloading photos", d, n))
    P["path"] = P.pid.map(lambda p: dl[p][0]); P["download_error"] = P.pid.map(lambda p: dl[p][1])

    # analyse (cached by file content so re-runs are fast)
    results = {}
    def work(r):
        if not r.path: return r.pid, {"ok": False, "error": r.download_error}
        key = f"{os.path.getsize(r.path)}_{r.file}_{r.claim_date}_{_CODE_STAMP}"
        if key in cache: return r.pid, cache[key]
        try: a = analyze_photo(r.path, r.claim_date)
        except Exception as e: a = {"ok": False, "error": f"analysis failed: {e}"}
        a["_key"] = key; return r.pid, a
    done = 0
    with cf.ThreadPoolExecutor(C.OCR_WORKERS) as ex:
        for pid, a in ex.map(work, list(P.itertuples())):
            results[pid] = a; done += 1
            if a.get("ok") and a.get("_key"): cache[a["_key"]] = a
            say("Reading photos", done, len(P))
            if done % 20 == 0: json.dump(cache, open(cache_path, "w"), default=str)
    json.dump(cache, open(cache_path, "w"), default=str)
    fields = ["md5", "dhash", "format", "result", "stamp_dates", "stamp_time", "latlon", "latlon_valid", "coords_impossible",
              "stamp_app", "phone_watermark", "screenshot", "letterbox", "sparkle", "ai_metadata", "edit_software",
              "ocr_text", "odo_candidates", "exif_time", "exif_gps"]
    for fl in fields:
        P[fl] = P.pid.map(lambda p: results[p].get(fl))
    P["status"] = P.pid.map(lambda p: "ok" if results[p].get("ok") else "missing")
    P.loc[P.status != "ok", "result"] = "Photo missing / not downloaded"
    P["dhash"] = P.dhash.map(lambda h: int(h) if h is not None and str(h) != "nan" else None)

    say("Running fraud checks", 0, 1)
    P, claims = run_checks(P, claims)
    P["check_priority"] = check_priorities(P)

    say("Writing Excel report", 0, 1)
    out_path = os.path.join(out_dir, base + "_ODOMETER_AUDIT.xlsx")
    tmp = tempfile.mkdtemp(prefix="odoaudit_")
    failed = int((P.status != "ok").sum())
    meta = {"input": os.path.basename(input_path), "run_time": datetime.now().strftime("%d-%b-%Y %H:%M"), "version": __version__,
            "log": [("Claim rows with odometer photos", len(claims)), ("Photo links", len(P)),
                    ("Photos downloaded / read", int((P.status == "ok").sum())), ("Photos that failed to download", failed),
                    ("Run time (minutes)", round((time.time() - t0) / 60, 1)), ("Full-size photos folder", photo_dir)]}
    try:
        write_report(P, claims, odo, meta, out_path, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    say("Done", 1, 1)
    # every photo an employee has (not only the flagged ones), so the screen can show them all
    photo_index = {}
    for r in P.itertuples():
        d = pd.to_datetime(r.claim_date, errors="coerce")
        photo_index.setdefault(str(r.emp), []).append({
            "pid": int(r.pid), "claim": str(r.claim_id), "side": r.side,
            "date": "" if pd.isna(d) else d.strftime("%d-%b-%Y"),
            "ok": r.result == C.RESULT_OK})
    return {"output": out_path, "photos": len(P), "claims": len(claims), "failed": failed,
            "non_compliant_photos": int((P.result != C.RESULT_OK).sum()),
            "high_flags": int((P.flag_priority == 0).sum()), "minutes": round((time.time() - t0) / 60, 1),
            # the download folder and, for each photo number in the report, the file on disk
            "photo_dir": photo_dir,
            "photo_files": {str(int(r.pid)): os.path.basename(r.path) for r in P.itertuples() if r.path},
            "employee_photos": photo_index}
