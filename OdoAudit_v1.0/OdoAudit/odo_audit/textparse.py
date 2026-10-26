"""Turns the text read from a photo into stamp facts: dates, times, location, apps, screenshots."""
import re
from datetime import date

MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
MON = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

STATES = (r"andhra\s?pradesh|arunachal|assam|bihar|chhattisgarh|goa|gujarat|haryana|himachal|jharkhand|karnataka|kerala|"
          r"madhya\s?pradesh|maharashtra|manipur|meghalaya|mizoram|nagaland|odisha|orissa|punjab|rajasthan|sikkim|"
          r"tamil\s?nadu|telangana|tripura|uttar\s?pradesh|uttarakhand|west\s?bengal|delhi|chandigarh|puducherry|jammu|kashmir|ladakh")
STRONG_LOC = re.compile(rf"(ind[il1][ae]\b|\bindis\b|{STATES}|divisi|district|\blat\b|\blat[:.]|\blng\b|\blong\b|latitude|longitude|°|altitude|\bgmt\s*[+-]?\s*0?5)", re.I)
WEAK_LOC = re.compile(r"\b(road|rd|nagar|colony|sector|marg|layout|estate|village|street|lane|chowk|bazar|bazaar|market|"
                      r"block|phase|ward|taluk|tehsil|mandal|city|town|puram|pur|abad|halli|pally|palli|gali|address)\b", re.I)
LATLON = re.compile(r"(?:lat(?:itude)?\s*[:=]?\s*(-?\d{1,3}\.\d+)\D{0,12}?(?:long|lng|lon)(?:gitude)?\s*[:=]?\s*(-?\d{1,9}\.?\d*))"
                    r"|(\d{1,2}\.\d{3,})\s*°?\s*N\s*,?\s*(\d{2,3}\.\d{3,})\s*°?\s*E", re.I)
DMS = re.compile(r"(\d{1,2})\s*°\s*(\d{1,2})\s*'\s*([\d.]+)\"?\s*N\D{0,6}(\d{2,3})\s*°\s*(\d{1,2})\s*'\s*([\d.]+)\"?\s*E", re.I)
TIME = re.compile(r"\b([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)(?:\s*[:.]\s*([0-5]\d))?\s*(am|pm)?", re.I)

STAMP_APPS = {
    "GPS Map Camera": r"gps\s*map\s*camera",
    "Timestamp Camera": r"timestamp\s*camera",
    "Live shooting": r"live\s*shooting",
    "Index-number stamp app": r"index\s*number",
    "Geotag app": r"geotag|geo\s*tag",
}
PHONE_WATERMARKS = r"\b(vivo|redmi|xiaomi|oppo|realme|samsung|oneplus|poco|iqoo|motorola|moto|nothing|tecno|infinix|shot on)\b"
GALLERY_UI = r"\b(share|shure|edt|edit|delete|more|details|favourite|favorite|minute ago|minutes ago|hours ago|yesterday|lens|send)\b"


def norm(text: str) -> str:
    t = text.replace("\n", " ")
    t = re.sub(r"(?<![a-z])[0QD]ct(?=[\s.,\-]*\d)", "Oct", t, flags=re.I)   # OCR reads O as 0/Q/D
    t = re.sub(r"(?<=\d)0ct", "Oct", t, flags=re.I)
    t = re.sub(r"(\d)(?=(" + MON + r"))", r"\1 ", t, flags=re.I)     # 17Oct2026 -> 17 Oct2026
    t = re.sub(r"(" + MON + r")[a-z]*(?=\d)", r"\1 ", t, flags=re.I)  # Oct2026 -> Oct 2026
    return t


def _mk(y, m, d):
    try:
        y = int(y); y = y + 2000 if y < 100 else y
        return date(y, int(m), int(d))
    except Exception:
        return None


def find_dates(text: str, near: date | None = None) -> list:
    """All plausible dates in the text. Ambiguous dd/mm vs mm/dd is resolved using the claim date."""
    t = norm(text)
    out = []
    for g in re.finditer(rf"(?<!\d)(\d{{1,2}})\s*[-/. ]?\s*({MON})[a-z]*\.?[-/, ]*\s*(20\d\d)(?=\d{{1,2}}[:.]\d|\D|$)", t, re.I):
        out.append(_mk(g.group(3), MONTHS[g.group(2)[:3].lower()], g.group(1)))
    for g in re.finditer(rf"\b({MON})[a-z]*\.?\s*(\d{{1,2}})\s*[,. ]\s*(20\d\d)(?=\d{{1,2}}[:.]\d|\D|$)", t, re.I):
        out.append(_mk(g.group(3), MONTHS[g.group(1)[:3].lower()], g.group(2)))
    for g in re.finditer(r"(?<!\d)(20\d\d)\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})(?!\d)", t):
        out.append(_mk(g.group(1), g.group(2), g.group(3)))
    for g in re.finditer(r"(?<![\d])(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(20\d\d(?=\d{1,2}[:.]\d|\D|$)|\d\d(?!\d))", t):
        a, b, y = int(g.group(1)), int(g.group(2)), g.group(3)
        c1, c2 = _mk(y, b, a), _mk(y, a, b)          # dd/mm, mm/dd
        cands = [c for c in (c1, c2) if c]
        if near and len(cands) == 2:
            cands.sort(key=lambda c: abs((c - near).days))
        if cands:
            out.append(cands[0])
    good = []
    for d in out:
        if not d or d in good: continue
        if near is not None and abs((d - near).days) > 45:   # misread digits (e.g. 2028, December) - ignore
            continue
        if 2020 <= d.year <= 2035:
            good.append(d)
    return good


# A time zone offset ("GMT +05:30") looks exactly like a clock time. Reading it as the stamp
# time made every GPS Map Camera stamp report 05:30 instead of the time printed on the photo.
TZ_OFFSET = re.compile(r"gmt\s*[+-]?\s*$|[+-]\s*$", re.I)


def find_times(text: str) -> list:
    res = []
    t = norm(text)
    for g in TIME.finditer(t):
        if TZ_OFFSET.search(t[max(0, g.start() - 8):g.start()]):
            continue
        h, mi, ap = int(g.group(1)), int(g.group(2)), (g.group(4) or "").lower()
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        res.append((h, mi, int(g.group(3) or 0), bool(ap) or h > 12))
    return res


def _fix_coord(v: str, lo: float, hi: float) -> float:
    """OCR often drops the decimal point (77574268 -> 77.574268). Put it back where the value becomes valid."""
    x = float(v)
    if lo <= x <= hi or "." in v: return x
    for k in (1, 2, 3):
        if k < len(v):
            y = float(v[:k] + "." + v[k:])
            if lo <= y <= hi: return y
    return x


def find_latlon(text: str):
    t = norm(text)
    m = LATLON.search(t)
    if m:
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try: return _fix_coord(a, 6, 37.5), _fix_coord(b.rstrip("."), 68, 97.5)
        except Exception: pass
    m = DMS.search(t)
    if m:
        g = [float(x) for x in m.groups()]
        return g[0] + g[1] / 60 + g[2] / 3600, g[3] + g[4] / 60 + g[5] / 3600
    return None


def location_evidence(text: str) -> tuple:
    strong = {x.group(0).lower() for x in STRONG_LOC.finditer(text)}
    weak = {x.group(0).lower() for x in WEAK_LOC.finditer(text)}
    has = bool(strong) or len(weak) >= 2
    return has, sorted(strong | weak)


def stamp_apps(text: str) -> list:
    return [name for name, rx in STAMP_APPS.items() if re.search(rx, text, re.I)]


def phone_watermark(text: str):
    m = re.search(PHONE_WATERMARKS, text, re.I)
    return m.group(1) if m else None


def gallery_ui_words(text: str) -> list:
    return sorted({m.group(1).lower() for m in re.finditer(GALLERY_UI, text, re.I)})


def odometer_candidates(lines: list) -> list:
    """Numbers that look like an odometer reading (4-7 digits, optionally one decimal), ignoring stamp lines."""
    out = []
    for txt in lines:
        low = txt.lower()
        if find_dates(txt) or ":" in txt or "lat" in low or "gmt" in low or "°" in txt or "," in txt \
                or STRONG_LOC.search(txt) or WEAK_LOC.search(txt) or "index" in low or "pin" in low:
            continue
        for m in re.finditer(r"(?<![\d.:/])(\d{4,7})(?:\.(\d))?(?![\d/:])", txt.replace(" ", "")):
            out.append(float(m.group(1) + ("." + m.group(2) if m.group(2) else "")))
    return out


BAD_COORD = re.compile(r"\b(lat|lng|long|lon)[a-z]*\s*[:=]?\s*-?(\d{4,})(\.\d+)?", re.I)
def impossible_coords(text: str) -> bool:
    """Lat/long written with impossible values (e.g. 'Lat 12454359.000000') - sign of an edited stamp.
    OCR often drops the decimal point, so a number without a point is accepted if a point can be
    placed to give a valid India coordinate."""
    for m in BAD_COORD.finditer(norm(text)):
        kind, ip, dec = m.group(1).lower(), m.group(2), m.group(3)
        if dec:                       # explicit point after 4+ digits: impossible
            return True
        rng = (6, 37.5) if kind == "lat" else (68, 97.5)
        ok = any(rng[0] <= float(ip[:k] + "." + ip[k:]) <= rng[1] for k in (1, 2, 3) if k < len(ip))
        if not ok:
            return True
    return False


def stamp_time(text: str, near=None) -> str:
    """Time printed next to the stamp date (HH:MM, 24h). Empty if not found.

    A time with AM/PM or seconds is unambiguous and wins. Stamps that print 24-hour time
    without either ("17-10-2026 09:35") are still a time: on a line that already carries the
    stamp date, a HH:MM pattern is taken as is - otherwise 09:35 was dropped while 14:05 was
    kept, which silently disabled the END-before-START check for morning photos.
    """
    segs = [x.strip() for x in text.split("|")]
    for i, seg in enumerate(segs):
        if find_dates(seg, near):
            fallback = ""
            for cand in (seg, segs[i + 1] if i + 1 < len(segs) else ""):
                for h, mi, sec, sure in find_times(cand):
                    if sure or sec: return f"{h:02d}:{mi:02d}"
                    fallback = fallback or f"{h:02d}:{mi:02d}"
            if fallback: return fallback
    return ""
