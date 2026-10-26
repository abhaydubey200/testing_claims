"""All settings in one place. Change values here; no other file needs editing."""

# ---- input columns (Bizom claim report) ----
COL_START = "Odometer Image of Start"
COL_END = "Odometer Image of End"
COL_EMP = "Employee_code"
COL_NAME = "User_Name"
COL_CLAIM = "Claim_Id"
COL_DETAIL = "Claimdetail_Id"
COL_DATE = "Claim_Date"
COL_SUBMIT = "Claim Submit Date"
COL_AMOUNT = "Claim_Amount"
COL_L1 = "First_level_Approver"
COL_KM = "Total KM Travelled"          # used for the KM check if Bizom fills it

# Optional: rupees paid per km by vehicle type, used for the KM check when the KM column is empty.
# Leave empty to skip. Example: {"Bike": 4.0, "Car": 10.0}
RATE_PER_KM = {}

# ---- downloading ----
DOWNLOAD_THREADS = 8
DOWNLOAD_TIMEOUT = 30          # seconds per photo
DOWNLOAD_RETRIES = 3

# ---- photo reading ----
OCR_MAX_SIDE = 1600            # photos are resized to this before reading (speed vs accuracy)
OCR_MIN_SIDE = 1100            # small photos are enlarged to this
OCR_WORKERS = 2                # photos read in parallel (raise on a fast PC)

# ---- checks ----
NEAR_DUPLICATE_MAX_DISTANCE = 10   # image-fingerprint distance (0-256) treated as "same photo"
SPARKLE_FLAG_SCORE = 0.85          # AI sparkle-mark score at or above which a photo is flagged
INDIA_LAT = (6.0, 37.5)
INDIA_LON = (68.0, 97.5)
MAX_DAILY_KM = 400                 # odometer distance above this in one claim is flagged
KM_TOLERANCE_PCT = 25              # KM claimed vs odometer difference allowed (%)
KM_TOLERANCE_ABS = 10              # ...and at least this many km

# ---- report ----
THUMB_SIZE = (150, 125)
RESULT_OK = "Timestamp + Location"
RESULTS = [
    "Timestamp + Location",
    "Timestamp only (no location)",
    "Location only (no timestamp)",
    "No stamp",
    "No stamp - gallery screenshot",
    "Photo missing / not downloaded",
]
