"""FastAPI backend for the Odometer Photo Audit screen.

Serves the built React app from web/dist and exposes the same features the
Streamlit screen had: settings, file list, upload, run with live progress,
report download and the Red Flags / Employee Summary tabs.
"""
import asyncio
import glob
import json
import os
import re
import sys
import threading
import traceback
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from io import BytesIO

# The .venv bundled with this project owns pandas/pyarrow/openpyxl/fastapi/uvicorn.
# When server.py is started by RUN_APP.bat, the batch sets PYTHONPATH=<root> so that
# "from odo_audit import ..." resolves. A leftover PYTHONHOME in the environment (set by
# some other tool, e.g. another Python install) would re-point the stdlib search to an
# unrelated prefix and drop the venv site-packages from sys.path, which is what made
# server.py report "No module named 'pandas'" even though the same interpreter imported
# pandas when run interactively.
#
# Defend against both: clear PYTHONHOME so the venv's own stdlib/site-packages are used,
# and ensure the project root is on sys.path so the odo_audit package is importable.
import os as _os
_ROOT = os.path.dirname(os.path.abspath(__file__))
_orig_pythonhome = _os.environ.get("PYTHONHOME")
_os.environ.pop("PYTHONHOME", None)
import logging as _logging
_logging.basicConfig(level=_logging.INFO, format="server.py: %(message)s", stream=sys.stderr)
_logging.info("PYTHONHOME before clear: %s", _orig_pythonhome)
_logging.info("PYTHONHOME after clear: %s", _os.environ.get("PYTHONHOME"))
_logging.info("sys.prefix before: %s", sys.prefix)
_logging.info("sys.executable before: %s", sys.executable)
_logging.info("sys.path before: %s", sys.path)
_venv_site = os.path.join(_ROOT, ".venv", "Lib", "site-packages")
if os.path.isdir(_venv_site) and _venv_site not in sys.path:
    sys.path.insert(0, _venv_site)
_project_root = os.path.abspath(_ROOT)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from PIL import Image, ImageOps
from pydantic import BaseModel

from odo_audit import config as C, __version__
from odo_audit.downloader import safe_name
from odo_audit.pipeline import run

ROOT = _ROOT
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
DIST = os.path.join(ROOT, "web", "dist")

@asynccontextmanager
async def lifespan(_app):
    """Open the browser once when started by RUN_APP.bat, and show the last report again."""
    try:
        _restore_last_run()
    except Exception:
        traceback.print_exc()
    if os.environ.get("ODOAUDIT_OPEN_BROWSER") == "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8501")).start()
    yield


app = FastAPI(title="Odometer Photo Audit", docs_url=None, redoc_url=None, lifespan=lifespan)

# ---------------- run state: one run at a time, like the old screen ----------------
_lock = threading.Lock()
_state = {"status": "idle", "stage": "", "done": 0, "total": 0,
          "error": "", "traceback": "", "result": None}
_tabs_cache = {}


# ---------------- reopen the last report after a restart ----------------
def _sheet(book, name):
    """Header name -> column index, plus the data rows of one sheet."""
    if name not in book.sheetnames:
        return {}, []
    rows = book[name].iter_rows(values_only=True)
    header = next(rows, None) or ()
    index = {str(h).strip(): i for i, h in enumerate(header) if h is not None}
    return index, [r for r in rows]


def _restore_last_run():
    """Rebuild the in-memory run state from the newest report on disk.

    The run state only lives in memory, so a restart used to lose every result and every
    photo. The workbook and the downloaded photo files are still there: read them back so
    the screen shows the last audit (with working photos) without running it again.
    """
    reports = [p for p in glob.glob(os.path.join(DATA, "*_ODOMETER_AUDIT.xlsx"))
               if not os.path.basename(p).startswith("~$")]
    if not reports:
        return None
    path = max(reports, key=os.path.getmtime)
    result = _result_from_report(path)
    with _lock:
        if _state["status"] == "running" or _state["result"]:
            return None
        _state.update(status="done", stage="Done", done=1, total=1,
                      error="", traceback="", result=result)
    return result


def _result_from_report(path: str) -> dict:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        # the download folder is written on the Summary sheet
        folder = ""
        minutes = 0
        for row in _sheet(book, "Summary")[1]:
            label = str(row[0]).strip() if row and row[0] is not None else ""
            if label == "Full-size photos folder" and len(row) > 1 and row[1]:
                folder = str(row[1]).strip()
            elif label == "Run time (minutes)":
                try:
                    minutes = float(row[1])
                except (TypeError, ValueError, IndexError):
                    pass

        base = os.path.basename(path)
        stem = base[:-len("_ODOMETER_AUDIT.xlsx")] if base.endswith("_ODOMETER_AUDIT.xlsx") else base
        beside = os.path.join(DATA, stem + "_photos")
        photo_dir = next((d for d in (folder, beside) if d and os.path.isdir(d)), beside)
        photo_dir = os.path.realpath(photo_dir)

        # photo number -> file name, matched on the names the downloader writes
        files = []
        if os.path.isdir(photo_dir):
            files = [(os.path.splitext(f)[0], f) for f in os.listdir(photo_dir)
                     if not f.startswith("_") and os.path.isfile(os.path.join(photo_dir, f))]

        pid_col, emp_col, claim_col, key_col, side_col, date_col, res_col, lvl_col = (
            "Photo #", "Employee_code", "Claim_Id", "Claim Key", "Side", "Claim_Date",
            "App Result", "Flag Level")
        cols, rows = _sheet(book, "Photo Review")

        def get(row, name):
            i = cols.get(name, -1)
            return row[i] if 0 <= i < len(row) else None

        photo_files, by_employee = {}, {}
        photos = failed = non_compliant = high_flags = 0
        for row in rows:
            pid = get(row, pid_col)
            if pid is None:
                continue
            try:
                pid = int(float(pid))
            except (TypeError, ValueError):
                continue
            photos += 1
            emp = str(get(row, emp_col) or "")
            claim = get(row, claim_col)
            claim = "" if claim is None else (str(int(claim)) if isinstance(claim, float) and claim.is_integer() else str(claim))
            key, side = get(row, key_col), str(get(row, side_col) or "")
            result = str(get(row, res_col) or "")
            failed += result == C.RESULTS[-1]
            non_compliant += result != C.RESULT_OK
            high_flags += str(get(row, lvl_col) or "") == "High"

            # the downloader names files  <employee>_<claim>_R<claim key>_<side>.<ext>
            name = None
            if emp and key is not None and side:
                expected = safe_name(f"{emp}_{claim}_R{key}_{side}")
                name = next((f for s, f in files if s == expected), None)
                if name is None:                    # number formatting differs: match the parts
                    digits = re.sub(r"\D", "", claim)
                    end = f"_R{key}_{side}"
                    for s, f in files:
                        if s.startswith(emp + "_") and s.endswith(end) and digits:
                            middle = re.sub(r"\D", "", s[len(emp) + 1:len(s) - len(end)])
                            if middle == digits:
                                name = f
                                break
            if name:
                photo_files[str(pid)] = name

            day = get(row, date_col)
            if isinstance(day, datetime):
                day = day.strftime("%d-%b-%Y")
            elif day is None or (isinstance(day, float) and pd.isna(day)):
                day = ""
            else:
                day = str(day)
            by_employee.setdefault(emp, []).append(
                {"pid": pid, "claim": claim, "side": side, "date": day,
                 "ok": result == C.RESULT_OK})

        claims = sum(1 for row in _sheet(book, "Claim Review")[1] if row and row[0] is not None)
    finally:
        book.close()

    return {"output": path, "photos": photos, "claims": claims, "failed": failed,
            "non_compliant_photos": non_compliant, "high_flags": high_flags,
            "minutes": round(minutes, 1), "photo_dir": photo_dir,
            "photo_files": photo_files, "employee_photos": by_employee}


class SettingsIn(BaseModel):
    download_threads: int | None = None
    ocr_workers: int | None = None
    bike_rate: float | None = None
    car_rate: float | None = None
    sparkle_score: float | None = None


class RunIn(BaseModel):
    file: str


def _list_files():
    out = []
    for f in glob.glob(os.path.join(DATA, "*")):
        base = os.path.basename(f)
        if not f.lower().endswith((".csv", ".xlsx", ".xls")):
            continue
        if "_ODOMETER_AUDIT" in base or base.startswith("~$"):
            continue
        out.append({"name": base, "size": os.path.getsize(f),
                    "mtime": os.path.getmtime(f),
                    "added": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d-%b-%Y %H:%M")})
    out.sort(key=lambda x: -x["mtime"])
    return out


def _data_path(name: str) -> str:
    """Resolve a file name to a path inside data/, rejecting anything else."""
    path = os.path.realpath(os.path.join(DATA, os.path.basename(name)))
    if not path.startswith(os.path.realpath(DATA) + os.sep):
        raise HTTPException(400, "Bad file name.")
    return path


# ---------------- settings ----------------
@app.get("/api/settings")
def get_settings():
    return {"download_threads": C.DOWNLOAD_THREADS, "ocr_workers": C.OCR_WORKERS,
            "bike_rate": float(C.RATE_PER_KM.get("Bike", 0.0)),
            "car_rate": float(C.RATE_PER_KM.get("Car", 0.0)),
            "sparkle_score": C.SPARKLE_FLAG_SCORE,
            "version": __version__}


@app.post("/api/settings")
def set_settings(s: SettingsIn):
    if s.download_threads is not None:
        C.DOWNLOAD_THREADS = max(2, min(16, s.download_threads))
    if s.ocr_workers is not None:
        C.OCR_WORKERS = max(1, min(6, s.ocr_workers))
    if s.sparkle_score is not None:
        C.SPARKLE_FLAG_SCORE = max(0.70, min(0.98, s.sparkle_score))
    if s.bike_rate is not None or s.car_rate is not None:
        rates = dict(C.RATE_PER_KM)
        if s.bike_rate is not None:
            rates["Bike"] = max(0.0, min(50.0, s.bike_rate))
        if s.car_rate is not None:
            rates["Car"] = max(0.0, min(50.0, s.car_rate))
        C.RATE_PER_KM = {k: v for k, v in rates.items() if v > 0}
    return get_settings()


# ---------------- files ----------------
@app.get("/api/files")
def list_files():
    return _list_files()


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = os.path.basename(file.filename or "")
    if not name or name.startswith("~$") or not name.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(400, "Upload a CSV or Excel claim extract (.csv, .xlsx, .xls).")
    dest = os.path.join(DATA, name)
    with open(dest, "wb") as fh:
        while chunk := await file.read(1024 * 1024):
            fh.write(chunk)
    return {"name": name, "saved": dest}


# ---------------- run + progress ----------------
def _runner(path: str):
    def prog(stage, done, total):
        with _lock:
            _state.update(stage=stage, done=done, total=total)
    try:
        res = run(path, DATA, progress=prog)
        with _lock:
            _state.update(status="done", stage="Done", done=1, total=1, result=res)
        try:                                    # warm the tab cache so the UI is instant
            _read_tabs(res["output"])
        except Exception:
            pass
    except Exception as e:
        with _lock:
            _state.update(status="error", error=str(e), traceback=traceback.format_exc())


@app.post("/api/run")
def start_run(r: RunIn):
    path = _data_path(r.file)
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found in data folder: {r.file}")
    with _lock:
        if _state["status"] == "running":
            raise HTTPException(409, "A run is already in progress.")
        _state.update(status="running", stage="Reading claim file", done=0, total=0,
                      error="", traceback="", result=None)
    threading.Thread(target=_runner, args=(path,), daemon=True).start()
    return {"started": True}


@app.get("/api/progress")
def progress():
    with _lock:
        return dict(_state)


@app.get("/api/progress/stream")
async def progress_stream():
    """Server-Sent Events: pushes the run state whenever it changes; the connection stays
    open (a keepalive comment goes out every ~15s) so the screen needs no polling."""
    async def gen():
        last, since = None, 0
        while True:
            with _lock:
                payload = json.dumps(dict(_state))
            if payload != last:
                yield f"data: {payload}\n\n"
                last, since = payload, 0
            else:
                since += 1
                if since % 50 == 0:            # ~15s without a change
                    yield ": keepalive\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ---------------- results ----------------
@app.get("/api/report")
def report():
    with _lock:
        res = _state["result"]
    if not res or not os.path.exists(res["output"]):
        raise HTTPException(404, "No report yet. Run an audit first.")
    return FileResponse(res["output"], media_type=(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        filename=os.path.basename(res["output"]))


def _read_tabs(path: str):
    # Keyed by the report's write time as well: a re-run writes the same file name, and a
    # path-only key kept serving the previous run's Red Flags / Employee Summary tabs.
    key = (path, os.path.getmtime(path))
    if key in _tabs_cache:
        return _tabs_cache[key]
    flags = pd.read_excel(path, sheet_name="Red Flags")
    emps = pd.read_excel(path, sheet_name="Employee Summary")
    data = {"red_flags": json.loads(flags.to_json(orient="records", date_format="iso")),
            "employees": json.loads(emps.to_json(orient="records", date_format="iso"))}
    _tabs_cache[key] = data
    return data


@app.get("/api/tabs")
def tabs():
    with _lock:
        res = _state["result"]
    if not res or not os.path.exists(res["output"]):
        raise HTTPException(404, "No report yet. Run an audit first.")
    try:
        return _read_tabs(res["output"])
    except Exception as e:
        raise HTTPException(500, f"Could not read the report: {e}")


@app.post("/api/reset")
def reset():
    with _lock:
        if _state["status"] == "running":
            raise HTTPException(409, "A run is still in progress — wait for it to finish first.")
        _state.update(status="idle", stage="", done=0, total=0, error="", traceback="", result=None)
    _tabs_cache.clear()
    return {
        "output": "",
        "photos": 0,
        "claims": 0,
        "failed": 0,
        "non_compliant_photos": 0,
        "high_flags": 0,
        "minutes": 0,
        "photo_dir": "",
        "photo_files": {},
        "employee_photos": {},
    }


def _photo_path(pid: int) -> str:
    """Resolve a photo number from the current report to a file inside its download folder."""
    with _lock:
        res = _state["result"]
    if not res:
        try:
            _restore_last_run()
        except Exception:
            traceback.print_exc()
        with _lock:
            res = _state["result"]
    name = ((res or {}).get("photo_files") or {}).get(str(pid))
    folder = os.path.realpath((res or {}).get("photo_dir") or "")
    if not name or not folder:
        raise HTTPException(404, "No photo for that number in the current report.")
    path = os.path.realpath(os.path.join(folder, name))
    if not path.startswith(folder + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, "The downloaded photo is missing.")
    return path


@app.get("/api/photo/{pid}")
def photo(pid: int):
    """Serve one downloaded photo from the current run, so the screen can open it."""
    return FileResponse(_photo_path(pid), headers={"Cache-Control": "private, max-age=3600"})


@lru_cache(maxsize=600)
def _thumbnail(path: str, stamp: float, size: int) -> bytes:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((size, size))
        out = BytesIO()
        im.save(out, "JPEG", quality=82)
        return out.getvalue()


@app.get("/api/photo/{pid}/thumb")
def photo_thumb(pid: int, size: int = 240):
    """A small preview of a downloaded photo, built on first request and cached."""
    path = _photo_path(pid)
    size = max(80, min(640, size))
    try:
        data = _thumbnail(path, os.path.getmtime(path), size)
    except Exception:
        raise HTTPException(404, "Could not read the photo.")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


# ---------------- the React app (registered last so /api/* wins) ----------------
if os.path.isdir(DIST):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
else:
    @app.get("/")
    def missing_ui():
        return JSONResponse(
            {"error": "The screen is not built yet. Run SETUP.bat once (needs Node.js) "
                      "to build the React app in web/."},
            status_code=503)
