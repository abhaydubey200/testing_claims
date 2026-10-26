"""Reads one photo: fingerprints, metadata, text on the photo (OCR), AI mark, screenshot signs."""
import hashlib, io, re
import numpy as np
from PIL import Image, ImageOps, ExifTags
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception:
    pass
from . import config as C, textparse as tp
from .sparkle import sparkle_score

_OCR = None
def ocr_engine():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR

# Byte strings that mean "an AI tool touched this file". Two entries were removed after an
# accuracy check on a real run: a bare b"jumb" is a 4-byte C2PA box name that also turns up by
# chance inside compressed pixel data (one false "AI-generated" High flag), and a bare
# b"Photoshop" matches the "Photoshop 3.0" APP13 header that any tool writing an ICC profile
# leaves behind (two false "edited" flags). Real Photoshop work still shows up as the XMP
# creator tool "Adobe Photoshop" or in the EXIF Software tag, both still checked below.
AI_META = [b"c2pa", b"SynthID", b"Gemini", b"Google AI", b"Imagen", b"Made with AI", b"trainedAlgorithmicMedia",
           b"compositeWithTrainedAlgorithmicMedia", b"DALL", b"Midjourney", b"Firefly", b"Stable Diffusion", b"Bing Image Creator",
           b"Meta AI", b"ChatGPT", b"OpenAI", b"Magic Editor", b"Adobe Photoshop", b"Snapseed", b"PicsArt", b"Canva", b"Lightroom"]
EDIT_ONLY = {b"Adobe Photoshop", b"Snapseed", b"PicsArt", b"Canva", b"Lightroom", b"Magic Editor"}


def dhash(img: Image.Image, size=16) -> int:
    g = np.asarray(img.convert("L").resize((size + 1, size)), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _ocr(img: Image.Image):
    arr = np.asarray(img.convert("RGB"))[:, :, ::-1]
    res, _ = ocr_engine()(arr)
    return [(r[1], float(r[2])) for r in (res or []) if float(r[2]) >= 0.5]


def _fit(img: Image.Image) -> Image.Image:
    w, h = img.size; L = max(w, h)
    if L > C.OCR_MAX_SIDE: s = C.OCR_MAX_SIDE / L
    elif L < C.OCR_MIN_SIDE: s = C.OCR_MIN_SIDE / L
    else: return img
    return img.resize((int(w * s), int(h * s)), Image.LANCZOS)


def _letterbox(gray: np.ndarray) -> bool:
    h = gray.shape[0]; band = max(1, int(h * 0.08))
    top, bot = gray[:band], gray[-band:]
    return bool(top.mean() < 12 and top.std() < 6 and bot.mean() < 12 and bot.std() < 6)


def analyze_photo(path: str, claim_date=None) -> dict:
    r = {"ok": False}
    raw = open(path, "rb").read()
    r["md5"] = hashlib.md5(raw).hexdigest()
    r["format"] = path.rsplit(".", 1)[-1].upper()
    head = raw[:300000]
    hits = [k for k in AI_META if k.lower() in head.lower()]
    r["ai_metadata"] = ", ".join(h.decode() for h in hits if h not in EDIT_ONLY)
    r["edit_software"] = ", ".join(h.decode() for h in hits if h in EDIT_ONLY)
    try:
        img = Image.open(io.BytesIO(raw))
        exif = img.getexif()
        r["exif_time"] = str(exif.get(306) or exif.get_ifd(0x8769).get(36867) or "")
        gps = exif.get_ifd(0x8825)
        r["exif_gps"] = bool(gps and (2 in gps or 4 in gps))
        sw = str(exif.get(305) or "")
        if sw and re.search(r"photoshop|snapseed|picsart|canva|lightroom|gemini|editor", sw, re.I):
            r["edit_software"] = (r["edit_software"] + ", " + sw).strip(", ")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        r["error"] = f"Cannot open image: {e}"
        return r
    r["width"], r["height"] = img.size
    r["dhash"] = dhash(img)
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    r["letterbox"] = _letterbox(gray)
    r["sparkle"] = round(sparkle_score(gray), 3)

    base = _fit(img); W, H = base.size
    lines = _ocr(base)
    strip = base.crop((0, int(H * 0.62), W, H)); strip = strip.resize((W * 2, strip.height * 2), Image.LANCZOS)
    lines += _ocr(strip)
    text = " | ".join(t for t, _ in lines)
    if not tp.find_dates(text, claim_date):
        for ang in (90, 270):
            more = _ocr(base.rotate(ang, expand=True))
            if tp.find_dates(" ".join(t for t, _ in more), claim_date):
                lines += more; break
    text = " | ".join(t for t, _ in lines)
    r["ocr_text"] = text[:2000]
    r["odo_candidates"] = tp.odometer_candidates([t for t, _ in lines])
    classify(r, claim_date)
    r["ok"] = True
    return r


def classify(r: dict, claim_date=None):
    text = r.get("ocr_text", "")
    dates = tp.find_dates(text, claim_date)
    times = tp.find_times(text)
    ll = tp.find_latlon(text)
    has_loc, loc_words = tp.location_evidence(text)
    apps = tp.stamp_apps(text)
    wm = tp.phone_watermark(text)
    ui = tp.gallery_ui_words(text)
    r["stamp_dates"] = [d.isoformat() for d in dates]
    r["stamp_time"] = tp.stamp_time(text, claim_date)
    r["latlon"] = f"{ll[0]:.5f}, {ll[1]:.5f}" if ll else ""
    r["coords_impossible"] = tp.impossible_coords(text)
    r["latlon_valid"] = (not r["coords_impossible"]) and ((ll is None) or (C.INDIA_LAT[0] <= ll[0] <= C.INDIA_LAT[1] and C.INDIA_LON[0] <= ll[1] <= C.INDIA_LON[1]))
    r["stamp_app"] = ", ".join(apps)
    r["phone_watermark"] = wm or ""
    has_date = bool(dates)
    has_location = bool(ll) or has_loc or bool(apps and has_date and any(a != "Timestamp Camera" for a in apps))
    # a phone-brand frame carries only the date - not a location stamp
    if wm and not ll and not tp.STRONG_LOC.search(text):
        has_location = False
    screenshot = len(set(ui) & {"share", "edit", "edt", "delete", "more", "details", "send", "lens", "shure"}) >= 2 or any(
        "ago" in u for u in ui)
    r["screenshot"] = bool(screenshot)
    if has_date and has_location: res = "Timestamp + Location"
    elif has_date: res = "Timestamp only (no location)"
    elif ll or (has_loc and apps): res = "Location only (no timestamp)"
    elif screenshot: res = "No stamp - gallery screenshot"
    else: res = "No stamp"
    r["result"] = res
    return r
