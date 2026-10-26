"""Folder mode: audits every claim file in the data folder without opening the screen."""
import os, glob, sys
from odo_audit.pipeline import run
ROOT = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(ROOT, "data")
files = [f for f in glob.glob(os.path.join(DATA, "*")) if f.lower().endswith((".csv", ".xlsx", ".xls"))
         and "_ODOMETER_AUDIT" not in f and not os.path.basename(f).startswith("~$")]
if not files:
    print("No claim file in the data folder. Copy the Bizom extract into:", DATA); sys.exit(1)
last = {}
def prog(stage, d, n):
    if last.get(stage) != d and (d == n or d % 10 == 0 or n <= 1):
        print(f"  {stage}: {d}/{n}", flush=True); last[stage] = d
for f in files:
    print(f"\n=== {os.path.basename(f)} ===")
    try:
        r = run(f, DATA, progress=prog)
        print(f"  Saved: {r['output']}\n  Photos {r['photos']} | without stamp {r['non_compliant_photos']} | High flags {r['high_flags']} | failed downloads {r['failed']}")
    except Exception as e:
        print("  ERROR:", e)
