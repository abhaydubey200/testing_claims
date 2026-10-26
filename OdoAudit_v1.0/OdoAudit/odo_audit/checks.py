"""Fraud and consistency checks that compare photos with claims and with each other."""
from datetime import date, datetime
import itertools
import pandas as pd
from . import config as C
from .analyzer import hamming

HIGH, MED, LOW = "High", "Medium", "Low"


def _d(s):
    try: return date.fromisoformat(str(s)[:10])
    except Exception: return None


def _pick_readings(sc: list, ec: list):
    """Choose the most plausible START/END odometer pair from OCR candidates (OCR may drop the decimal point)."""
    def variants(v):
        out = {v}
        if v >= 10000: out.add(round(v / 10, 1))
        return out
    best = None
    for s in sc:
        for e in ec:
            for sv in variants(s):
                for ev in variants(e):
                    diff = ev - sv
                    if 0 <= diff <= C.MAX_DAILY_KM and (best is None or diff < best[2]):
                        best = (sv, ev, diff)
    return best


def run_checks(photos: pd.DataFrame, claims: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """photos: one row per photo with analysis fields; claims: one row per claim row.
    Adds 'flags' (list of (priority, category, text)) to photos and odometer fields to claims."""
    P = photos; P["flag_list"] = [[] for _ in range(len(P))]
    add = lambda i, pr, cat, txt: P.at[i, "flag_list"].append((pr, cat, txt))
    ok = P["status"] == "ok"

    # --- per-photo checks ---
    for i, r in P[ok].iterrows():
        cd, sd = r["claim_date"], r["submit_date"]
        ds = [_d(x) for x in (r.get("stamp_dates") or [])]
        ds = [x for x in ds if x]
        if ds and cd and cd not in ds:
            d0 = min(ds, key=lambda x: abs((x - cd).days))
            if d0 > cd:
                add(i, HIGH, "Photo dated after the claim date", f"Photo dated {d0:%d-%b-%Y}, claim date {cd:%d-%b-%Y}")
            else:
                add(i, MED, "Stamp date does not match claim", f"Photo dated {d0:%d-%b-%Y}, claim date {cd:%d-%b-%Y}")
            if sd and d0 > sd:
                add(i, HIGH, "Photo dated after claim was submitted", f"Photo dated {d0:%d-%b-%Y}, submitted {sd:%d-%b-%Y}")
        if r.get("coords_impossible"):
            add(i, HIGH, "Stamp looks edited", "Impossible GPS coordinates written in the stamp")
        elif r.get("latlon") and not r.get("latlon_valid", True):
            add(i, HIGH, "GPS outside India", f"Stamp GPS {r['latlon']} is outside India")
        if (r.get("sparkle") or 0) >= C.SPARKLE_FLAG_SCORE:
            add(i, HIGH, "Possible AI-edited photo", f"Sparkle mark like Google Gemini's AI mark found (score {r['sparkle']:.2f})")
        if r.get("ai_metadata"):
            add(i, HIGH, "Possible AI-generated photo", f"AI tool information inside the file: {r['ai_metadata']}")
        if r.get("edit_software"):
            add(i, MED, "Edited with photo software", f"Editing software recorded in the file: {r['edit_software']}")
        if r.get("screenshot"):
            add(i, LOW, "Screenshot instead of photo", "Phone gallery screen captured instead of the original photo")
        elif r.get("letterbox"):
            add(i, LOW, "Screenshot instead of photo", "Black bars above and below - looks like a screenshot of a photo")
        if r.get("format") in ("PNG",):
            add(i, LOW, "Unusual file type", "PNG file - usually a screenshot")

    # --- reused photos (identical files and near-identical images) ---
    okP = P[ok]
    for _, g in okP.groupby("md5"):
        if len(g) > 1:
            for i in g.index:
                others = g.drop(i)
                txt = "; ".join(f"same as #{o.pid} ({o.side}, claim {o.claim_id}, {o.claim_date:%d-%b})" for o in others.itertuples())
                pr = HIGH if any((o.side == P.at[i, "side"] and o.claim_date != P.at[i, "claim_date"]) or o.emp != P.at[i, "emp"]
                                 for o in others.itertuples()) else MED
                add(i, pr, "Reused photo", txt)
    hashes = [(i, r.dhash, r.md5) for i, r in okP.iterrows() if r.dhash is not None]
    for (i, h1, m1), (j, h2, m2) in itertools.combinations(hashes, 2):
        if m1 != m2 and hamming(int(h1), int(h2)) <= C.NEAR_DUPLICATE_MAX_DISTANCE:
            for a, b in ((i, j), (j, i)):
                o = P.loc[b]
                pr = HIGH if (o.emp != P.at[a, "emp"]) else MED
                add(a, pr, "Reused photo", f"near-identical to #{o.pid} ({o.side}, claim {o.claim_id}, {o.claim_date:%d-%b})")

    # --- claim-level checks ---
    claims["odo_start"] = None; claims["odo_end"] = None; claims["odo_km"] = None
    for ci, c in claims.iterrows():
        s = P[(P.claim_key == c.claim_key) & (P.side == "START") & ok]
        e = P[(P.claim_key == c.claim_key) & (P.side == "END") & ok]
        if s.empty or e.empty: continue
        si, ei = s.index[0], e.index[0]
        if P.at[si, "md5"] == P.at[ei, "md5"]:
            add(si, HIGH, "Same photo for START and END", "START and END are the same photo")
        # END stamped before START
        sd, ed = _d((P.at[si, "stamp_dates"] or [None])[0]), _d((P.at[ei, "stamp_dates"] or [None])[0])
        st, et = P.at[si, "stamp_time"], P.at[ei, "stamp_time"]
        if sd and ed and st and et:
            sdt = datetime.combine(sd, datetime.strptime(st, "%H:%M").time())
            edt = datetime.combine(ed, datetime.strptime(et, "%H:%M").time())
            if (sdt - edt).total_seconds() > 600:          # more than 10 minutes earlier
                add(ei, MED, "END photo taken before START", f"START {sdt:%d-%b %H:%M}, END {edt:%d-%b %H:%M}")
        sc_, ec_ = P.at[si, "odo_candidates"] or [], P.at[ei, "odo_candidates"] or []
        pick = _pick_readings(sc_, ec_)
        if not pick and sc_ and ec_:
            s1, e1 = max(sc_), max(ec_)
            if len(str(int(s1))) == len(str(int(e1))) and 0.9 < e1 / s1 < 1.0 and s1 - e1 > 1:
                add(ei, MED, "Odometer END below START", f"END reading {e1:g} is lower than START {s1:g} (OCR reading - verify)")
        if pick:
            claims.at[ci, "odo_start"], claims.at[ci, "odo_end"], claims.at[ci, "odo_km"] = pick
        km_claimed = c.get("km_claimed")
        if pick and km_claimed and km_claimed > 0:
            diff = km_claimed - pick[2]
            if diff > max(C.KM_TOLERANCE_ABS, pick[2] * C.KM_TOLERANCE_PCT / 100):
                add(ei, MED, "KM claimed above odometer", f"Claimed ~{km_claimed:.0f} km, odometer shows {pick[2]:.0f} km (OCR reading - verify)")

    # odometer going backwards across days (only where readings were read confidently)
    cr = claims.dropna(subset=["odo_start"]).sort_values(["emp", "claim_date", "claim_id"])
    for emp, g in cr.groupby("emp"):
        prev = None
        for c in g.itertuples():
            same_scale = prev is not None and prev.odo_end > 0 and 0.67 < c.odo_start / prev.odo_end < 1.5
            if same_scale and c.odo_start < prev.odo_end - 5 and c.claim_date != prev.claim_date:
                idx = P[(P.claim_key == c.claim_key) & (P.side == "START")].index
                if len(idx):
                    add(idx[0], MED, "Odometer reading goes backwards",
                        f"START {c.odo_start:g} is below previous END {prev.odo_end:g} ({prev.claim_date:%d-%b}) - OCR reading, verify")
            prev = c
    P["flag_text"] = P["flag_list"].map(lambda fl: " | ".join(f"[{p}] {cat}: {t}" for p, cat, t in fl))
    P["flag_priority"] = P["flag_list"].map(lambda fl: min((["High", "Medium", "Low"].index(p) for p, _, _ in fl), default=9))
    return P, claims
