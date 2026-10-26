# Odometer Photo Audit

Checks the odometer photos on Bizom **HQ-LOCAL TRAVEL (For 35KM+)** claims and finds:

- photos **without a timestamp and location stamp**
- **fake, reused, edited or AI-made** photos
- other **fraud signs** (dates that don't match the claim, odometer readings that don't add up)

It runs **entirely on your PC**. Photos are downloaded from Bizom's links and read on your computer. Nothing is sent anywhere else.

---

## 1. One-time setup (about 5 minutes, needs internet)

1. Install **Python 3.12** from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"** during install.
   - Python 3.10 and 3.11 also work. 3.13 does not yet, because the photo reader doesn't support it.
   - Also install **Node.js** from https://nodejs.org/. It is needed only once, so SETUP can build the screen.
2. Unzip this folder anywhere, for example `Documents\OdoAudit`.
3. Double-click **`SETUP.bat`**. It installs everything into a private `.venv` folder inside this one, so nothing else on the PC is changed, and builds the screen into `web/dist`.

## 2. Every month

**Screen mode (recommended)**

1. Double-click **`RUN_APP.bat`**. The app opens in your browser.
2. Drop the raw Bizom claim extract (CSV or Excel) onto the screen.
3. Click **Run audit** and wait. About 400 photos take roughly 10–20 minutes the first time.
4. Click **Download Excel report**. The report is also saved in the `data` folder.

**Folder mode**

1. Copy the Bizom file into `data`.
2. Double-click **`RUN_FOLDER_MODE.bat`**. The `data` folder opens when it's done.

**Re-running** the same file is fast: photos already downloaded and read are reused.

## 3. What you get: `<file>_ODOMETER_AUDIT.xlsx`

| Sheet | Contents |
|---|---|
| **Summary** | Live totals: photos, claims, ₹ on non-compliant claims, employees, red flags, HR-check progress |
| **Employee Summary** | One row per employee, worst first, with L1 approver, status and red flags |
| **Claim Review** | START and END result per claim, claim result, odometer readings |
| **Photo Review** | Thumbnail, result, stamp date/time/GPS, red flags, **HR Check** (column V), **Final Result**, link to the full photo |
| **Red Flags** | Findings grouped by employee, with priority and suggested action |
| **AI Mark Corner Check** | Bottom-right corner of every photo, so you can scan quickly by eye for the Gemini ✦ mark |
| **Raw Data with Photos** | The original Bizom rows, with the photos placed in the two odometer columns |

**Photo results**

- Timestamp + Location *(compliant)*
- Timestamp only (no location)
- Location only (no timestamp)
- No stamp
- No stamp – gallery screenshot
- Photo missing / not downloaded

## 4. Checks

| Priority | Check | How it is found |
|---|---|---|
| High | Photo dated **after the claim date** or **after the claim was submitted** | Date read from the stamp |
| High | **Stamp looks edited**: impossible GPS, or GPS outside India | Stamp text |
| High | **Possible AI-edited / AI-made photo** | Gemini sparkle mark; AI-tool information inside the file |
| High | **Same photo** used for START and END, used on two different days, or used by two employees | Image fingerprints (exact and near-identical) |
| Medium | **Reused photo**, e.g. yesterday's END sent again as today's START | Image fingerprints |
| Medium | **Stamp date ≠ claim date**; **END taken before START** | Stamp date and time |
| Medium | **Odometer END below START** or **readings going backwards** across days; **KM claimed above odometer** | Odometer read from the photo (verify) |
| Medium | Edited with photo software (Snapseed, PicsArt, Photoshop…) | Information inside the file |
| Low | Screenshot instead of a camera photo; PNG files | Gallery buttons on screen, black bars, file type |

The **KM check** runs only if Bizom fills *Total KM Travelled*, or if you enter a ₹-per-km rate in the app's sidebar.

## 5. How accurate it is: check before sending

This tool was tested on the October 2026 file (402 photos) against a full manual review:

- **97.8% agreement** on compliant vs not compliant.
- **All 237** photos with no stamp were found correctly.
- **8 stamped photos were missed** because their text was too small to read. They show as "No stamp" and go into the HR check list.
- It found the same key fraud cases as the manual review: photos dated after the claim, an edited stamp, AI-mark photos, reused photos, and wrong dates.

The test used reduced-size photos. Real runs download full-size photos, which read better.

**Known limits**

- **The AI sparkle detector** only flags clear cases. Always scan the *AI Mark Corner Check* sheet.
- **Odometer readings** are read automatically and can be wrong. Odometer flags say "verify".
- **The app suggests, HR decides.** In *Photo Review*, filter column **U (Check Priority)**. Open each marked photo full size, then set column **V**: Correct, or Wrong. Every total updates. If the random sample (priority 3) finds 2 or more wrong results, check more photos before sending.

## 6. Settings

Everyday settings are in the app's sidebar. All other settings are in `odo_audit/config.py`, including column names (if Bizom changes them), download speed, thresholds and India GPS limits.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| SETUP says Python not found | Install Python 3.12 with "Add to PATH", then run SETUP again |
| SETUP fails installing packages | Office proxy. Ask IT for the proxy and see the message in the SETUP window |
| SETUP says Node.js was not found | Install Node.js from https://nodejs.org/ then run SETUP.bat again |
| Many "Photo missing / not downloaded" | Check that the photo links open in a browser on this PC |
| Missing columns error | Bizom renamed a column. Update the names at the top of `odo_audit/config.py` |
| Slow | Raise "Photos read at once" in the sidebar on a fast PC |

## Folder layout

```
OdoAudit/
  RUN_APP.bat           start the screen
  RUN_FOLDER_MODE.bat   audit everything in data/
  SETUP.bat             one-time install
  server.py             local API server: runs the audit and serves the screen
  web/                  the React screen (SETUP.bat builds it into web/dist)
  run_folder_mode.py
  requirements.txt
  odo_audit/            the engine: loader, downloader, analyzer, checks, report, config
  data/                 put Bizom files here; results come back here
```
