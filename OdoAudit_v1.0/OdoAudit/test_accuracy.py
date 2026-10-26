"""Accuracy test for the per-photo stamp verdict.

The audit is only useful if the verdict on each photo is right, so this file measures it
against a human answer sheet instead of trusting the classifier.

1) Build a review sample (downscaled copies + an empty answer sheet):

       .venv/Scripts/python.exe test_accuracy.py sample --n 40

   The sample is stratified by the verdict the app produced, so the rare verdicts
   ("Location only", "gallery screenshot") are represented.  Photo names carry no
   verdict, so the person labelling does not see the answer.

2) Fill the `truth` column in accuracy/truth.csv with one of the labels in config.RESULTS.

3) Score it:

       .venv/Scripts/python.exe test_accuracy.py score

4) Optional: check the stamp-text reading on known stamp formats:

       .venv/Scripts/python.exe test_accuracy.py formats

The sample is drawn from a run's analysis cache (written by the pipeline next to the
downloaded photos), so re-running this file never re-downloads or re-reads photos.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import random
import re
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from odo_audit import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "accuracy")
TRUTH = os.path.join(OUT, "truth.csv")
PRED = os.path.join(OUT, "predictions.csv")
KEY_RX = re.compile(r"^\d+_(?P<file>.+)_(?P<date>\d{4}-\d{2}-\d{2})$")


def newest_run() -> str:
    """The most recently written analysis cache under data/."""
    data = os.path.join(HERE, "data")
    caches = []
    for name in os.listdir(data):
        path = os.path.join(data, name, "_analysis_cache.json")
        if os.path.isfile(path):
            caches.append(path)
    if not caches:
        sys.exit("No _analysis_cache.json found under data/. Run an audit first.")
    return max(caches, key=os.path.getmtime)


def load_run(cache_path: str) -> tuple[dict, str]:
    """{file name: analysis entry} plus the photo folder the cache lives in."""
    cache = json.load(open(cache_path, encoding="utf-8"))
    by_file = {}
    for key, entry in cache.items():
        m = KEY_RX.match(key)
        if not m:
            continue
        by_file[m.group("file")] = {**entry, "_claim_date": m.group("date")}
    return by_file, os.path.dirname(cache_path)


def sample(n: int, seed: int) -> None:
    by_file, photo_dir = load_run(newest_run())
    rows = sorted(by_file.items())
    if not rows:
        sys.exit("The analysis cache is empty.")

    # Stratified draw: proportional, but every verdict gets at least a few photos.
    groups = collections.defaultdict(list)
    for name, entry in rows:
        groups[entry.get("result") or "?"].append(name)
    rng = random.Random(seed)
    quota = {}
    for verdict, names in groups.items():
        share = max(3, round(n * len(names) / len(rows)))
        quota[verdict] = min(len(names), share)
    while sum(quota.values()) > n:                     # trim the largest group first
        big = max(quota, key=lambda v: quota[v])
        quota[big] -= 1
    while sum(quota.values()) < n:
        room = [v for v in quota if quota[v] < len(groups[v])]
        if not room:
            break
        quota[max(room, key=lambda v: len(groups[v]) - quota[v])] += 1

    picked = []
    for verdict, count in quota.items():
        picked += [(name, verdict) for name in rng.sample(groups[verdict], count)]
    rng.shuffle(picked)                                # no verdict order to read off

    img_dir = os.path.join(OUT, "sample")
    shutil.rmtree(img_dir, ignore_errors=True)
    os.makedirs(img_dir, exist_ok=True)

    from PIL import Image
    truth_rows, pred_rows = [], []
    for i, (name, verdict) in enumerate(picked, 1):
        src = os.path.join(photo_dir, name)
        if not os.path.isfile(src):
            print(f"  (skipped, file missing: {name})")
            continue
        short = f"{i:02d}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', name)}"
        dst = os.path.join(img_dir, short)
        try:
            img = Image.open(src)
            img.thumbnail((1100, 1100))
            img.convert("RGB").save(dst, "JPEG", quality=85)
        except Exception as exc:
            print(f"  (skipped, cannot open {name}: {exc})")
            continue
        truth_rows.append({"photo": short, "truth": "", "notes": ""})
        pred_rows.append({"photo": short, "predicted": verdict, "file": name})

    with open(TRUTH, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["photo", "truth", "notes"])
        w.writeheader()
        w.writerows(truth_rows)
    with open(PRED, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["photo", "predicted", "file"])
        w.writeheader()
        w.writerows(pred_rows)

    print(f"Sampled {len(truth_rows)} photos from {os.path.basename(os.path.dirname(photo_dir))}")
    for verdict, count in sorted(quota.items(), key=lambda kv: -kv[1]):
        print(f"  {count:3d}  {verdict}")
    print(f"\nImages:  {img_dir}")
    print(f"Answers: {TRUTH}  <- fill the 'truth' column")
    print("Labels:  " + " | ".join(C.RESULTS))


def _read_csv(path: str) -> list[dict]:
    if not os.path.isfile(path):
        sys.exit(f"{os.path.basename(path)} not found - run 'sample' first.")
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def score() -> None:
    truth = _read_csv(TRUTH)
    pred = {r["photo"]: r["predicted"] for r in _read_csv(PRED)}
    labelled = [r for r in truth if (r.get("truth") or "").strip()]
    if not labelled:
        sys.exit(f"No answers yet: fill the 'truth' column in {TRUTH}")

    allowed = set(C.RESULTS)
    bad = sorted({r["truth"].strip() for r in labelled} - allowed)
    if bad:
        sys.exit("Unknown labels (must match config.RESULTS):\n  " + "\n  ".join(bad))

    pairs = [(r["photo"], pred[r["photo"]], r["truth"].strip()) for r in labelled]
    right = sum(1 for _, p, t in pairs if p == t)
    print(f"Labelled photos: {len(pairs)}   correct: {right}   accuracy: {right / len(pairs):.1%}\n")

    # Per-verdict precision / recall / F1.
    labels = [v for v in C.RESULTS if any(v in (p, t) for _, p, t in pairs)]
    print(f"{'verdict':30s} {'n':>3s} {'precision':>10s} {'recall':>7s} {'f1':>6s}")
    print("-" * 60)
    for v in labels:
        tp = sum(1 for _, p, t in pairs if p == v and t == v)
        fp = sum(1 for _, p, t in pairs if p == v and t != v)
        fn = sum(1 for _, p, t in pairs if p != v and t == v)
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * prec * rec / (prec + rec) if tp and prec + rec else float("nan")
        print(f"{v:30s} {sum(1 for _, _, t in pairs if t == v):3d} {prec:10.2f} {rec:7.2f} {f1:6.2f}")

    print(f"\n{'app verdict \\ truth':30s} " + " ".join(f"{v[:9]:>9s}" for v in labels))
    for pv in labels:
        cells = [sum(1 for _, p, t in pairs if p == pv and t == tv) for tv in labels]
        print(f"{pv:30s} " + " ".join(f"{c:9d}" for c in cells))

    misses = [(ph, p, t) for ph, p, t in pairs if p != t]
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for ph, p, t in misses:
            print(f"  {ph}\n      app: {p}\n    truth: {t}")
    else:
        print("\nNo misses in this sample.")

    # The sample is stratified, so the plain accuracy above is not the population figure.
    # Reweight by how often each verdict occurs in the whole run.
    by_file, _ = load_run(newest_run())
    pop = collections.Counter((e.get("result") or "?") for e in by_file.values())
    total = sum(pop.values())
    weighted = sum(pop[t] / total * (sum(1 for _, p, t2 in pairs if p == t2 and t2 == t) /
                                      max(1, sum(1 for _, _, t2 in pairs if t2 == t)))
                   for t in labels if pop.get(t) and any(t2 == t for _, _, t2 in pairs))
    print(f"\nAccuracy weighted back to the full run ({total} photos): {weighted:.1%}")
    print("(Weighting uses the human label counts per verdict, so it is an estimate - "
          "widen the sample to tighten it.)")


FORMAT_CASES = [
    # (name, OCR text, expected verdict, expected stamp time or "")
    ("GPS Map Camera 3-line", "GPS Map Camera | Indore, Madhya Pradesh, India | Lat 22.719568, Long 75.857727 | 17/10/2026 09:35 AM GMT +05:30", "Timestamp + Location", "09:35"),
    ("GPS Map Camera no city", "GPS Map Camera | Lat 22.719568, Long 75.857727 | 17/10/2026 09:35 AM GMT +05:30", "Timestamp + Location", "09:35"),
    ("Timestamp Camera", "Timestamp Camera | 17 Oct 2026 09:35 AM", "Timestamp only (no location)", "09:35"),
    ("Timestamp Camera + place", "Timestamp Camera | MG Road, Indore | 17 Oct 2026 09:35 AM", "Timestamp only (no location)", "09:35"),
    ("Lat/Long words only", "Latitude: 22.719568 Longitude: 75.857727", "Location only (no timestamp)", ""),
    ("DMS format", "22\u00b043'10.4\"N 75\u00b051'27.8\"E", "Location only (no timestamp)", ""),
    ("decimal N/E", "22.719568\u00b0 N, 75.857727\u00b0 E", "Location only (no timestamp)", ""),
    ("dmy slash, short year", "17/10/26 09:35 AM", "Timestamp only (no location)", "09:35"),
    ("iso date + seconds", "2026-10-17 09:35:12", "Timestamp only (no location)", "09:35"),
    ("month first", "Oct 17, 2026 09:35 AM", "Timestamp only (no location)", "09:35"),
    ("date only", "17 Oct 2026", "Timestamp only (no location)", ""),
    ("index number app", "INDEX NUMBER | 17 Oct 2026 | 09:35 AM", "Timestamp + Location", "09:35"),
    ("live shooting", "live shooting | 17 Oct 2026 | 09:35 AM | Lat 22.719568 Long 75.857727", "Timestamp + Location", "09:35"),
    ("gps + address words", "17 Oct 2026 09:35 AM | 45 Vijay Nagar Colony, Indore, Madhya Pradesh", "Timestamp + Location", "09:35"),
    ("dot instead of colon", "17 Oct 2026 09.35 AM", "Timestamp only (no location)", "09:35"),
    ("24h, no am/pm", "17-10-2026 09:35", "Timestamp only (no location)", "09:35"),
    ("vivo phone frame", "vivo V27e | 17 Oct 2026", "Timestamp only (no location)", ""),
    ("24h after midnight", "17-10-2026 14:05", "Timestamp only (no location)", "14:05"),
    # "GMT +05:30" is an offset, not a clock time - it used to win and report 05:30
    ("gps stamp, 24h + tz", "GPS Map Camera | Indore, Madhya Pradesh, India | Lat 22.719568, Long 75.857727 | 17/10/2026 18:53 GMT +05:30", "Timestamp + Location", "18:53"),
    ("date + tz, no clock", "GPS Map Camera | Lat 22.719568, Long 75.857727 | 17/10/2026 GMT +05:30", "Timestamp + Location", ""),
]


def formats() -> None:
    from odo_audit.analyzer import classify
    claim_date = date(2026, 10, 17)
    fails = 0
    for name, text, want, want_time in FORMAT_CASES:
        r = {"ocr_text": text}
        classify(r, claim_date)
        got, got_time = r["result"], r["stamp_time"]
        ok = got == want and (want_time == "" or got_time == want_time)
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name:26s} {got:28s} time={got_time!r}"
              + ("" if ok else f"   (want {want!r} time={want_time!r})"))
    print(f"\n{len(FORMAT_CASES) - fails}/{len(FORMAT_CASES)} stamp formats read correctly")
    if fails:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="build a review sample and an empty answer sheet")
    s.add_argument("--n", type=int, default=40, help="photos to sample (default 40)")
    s.add_argument("--seed", type=int, default=1, help="sampling seed, so a sample can be reproduced")
    sub.add_parser("score", help="score the filled answer sheet")
    sub.add_parser("formats", help="check the stamp reading on known stamp formats")
    args = ap.parse_args()
    if args.cmd == "sample":
        sample(args.n, args.seed)
    elif args.cmd == "score":
        score()
    else:
        formats()


if __name__ == "__main__":
    main()
