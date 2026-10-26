"""Downloads photos in parallel into a cache folder (photos already downloaded are reused)."""
import os, re, time, concurrent.futures as cf
import requests
from . import config as C


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:80]


def fetch(url: str, dest: str) -> None:
    last = None
    for attempt in range(C.DOWNLOAD_RETRIES):
        try:
            with requests.get(url, timeout=C.DOWNLOAD_TIMEOUT, stream=True) as r:
                r.raise_for_status()
                tmp = dest + ".part"
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(65536): f.write(chunk)
                os.replace(tmp, dest); return
        except Exception as e:
            last = e; time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed: {last}")


def download_all(jobs: list, folder: str, progress=None) -> dict:
    """jobs: list of (key, url, filename). Returns {key: (path or None, error or '')}."""
    os.makedirs(folder, exist_ok=True)
    out, done = {}, 0
    def one(job):
        key, url, fn = job; dest = os.path.join(folder, fn)
        if os.path.exists(dest) and os.path.getsize(dest) > 0: return key, dest, ""
        try: fetch(url, dest); return key, dest, ""
        except Exception as e: return key, None, str(e)
    with cf.ThreadPoolExecutor(C.DOWNLOAD_THREADS) as ex:
        for key, path, err in ex.map(one, jobs):
            out[key] = (path, err); done += 1
            if progress: progress(done, len(jobs))
    return out
