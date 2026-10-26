"""Reads the raw Bizom claim extract (CSV or Excel) and keeps the rows that carry odometer photos."""
import pandas as pd
from . import config as C


def load_claims(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (all_rows, odometer_rows). Raises ValueError with a plain message if columns are missing."""
    if path.lower().endswith(".csv"):
        try: df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError: df = pd.read_csv(path, dtype=str, encoding="latin-1")
    else:
        xl = pd.ExcelFile(path)
        sheet = next((s for s in xl.sheet_names if C.COL_START in pd.read_excel(xl, s, nrows=0).columns), None)
        if sheet is None:
            raise ValueError(f'No sheet has the column "{C.COL_START}".')
        df = pd.read_excel(xl, sheet, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    need = [C.COL_START, C.COL_END, C.COL_EMP, C.COL_NAME, C.COL_CLAIM, C.COL_DATE, C.COL_AMOUNT]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError("The file is missing these Bizom columns: " + ", ".join(miss))
    df["_row"] = range(2, len(df) + 2)                       # row number as in the source file
    for c in (C.COL_START, C.COL_END):
        df[c] = df[c].fillna("").str.strip()
    odo = df[(df[C.COL_START].str.startswith("http")) | (df[C.COL_END].str.startswith("http"))].copy()
    odo[C.COL_AMOUNT + "_num"] = pd.to_numeric(odo[C.COL_AMOUNT], errors="coerce").fillna(0.0)
    odo["_date"] = pd.to_datetime(odo[C.COL_DATE], errors="coerce", dayfirst=False).dt.date
    if C.COL_SUBMIT in odo:
        odo["_submit"] = pd.to_datetime(odo[C.COL_SUBMIT], errors="coerce").dt.date
    else:
        odo["_submit"] = None
    return df, odo.reset_index(drop=True)
