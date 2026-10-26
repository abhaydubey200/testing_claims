import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Loader2, RefreshCw, Search, X } from "lucide-react";

const FLAG_COLS = [
  "Priority",
  "Category",
  "Employee_code",
  "User_Name",
  "L1 Approver",
  "Photo #",
  "Claim_Id(s)",
  "Details",
  "Suggested Action",
];
const EMP_COLS = ["Employee_code", "User_Name", "HQ", "L1 Approver", "Red Flags (photos)"];

// Only these columns hold free text that needs to wrap; the rest stay on one line.
const WRAP_COLS = new Set(["Details", "Suggested Action"]);

// Meaning uses colour as text only (red wrong, yellow medium, grey low).
const TONE = { High: "text-red-400", Medium: "text-yellow-400", Low: "text-neutral-500" };

function cell(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number" && Number.isInteger(v)) return String(v);
  return String(v);
}

function Table({ rows, columns, query, onSelect, selectedRow }) {
  if (rows === null) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-border/70 bg-black/30 py-12 text-sm text-neutral-400">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Loading the report…
      </div>
    );
  }
  if (!rows.length) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
        <p className="text-sm text-neutral-300">{query ? "No matching rows" : "Nothing to show"}</p>
        <p className="mt-1 text-xs text-neutral-500">
          {query ? "Try a shorter search." : "This report has no rows for this tab."}
        </p>
      </div>
    );
  }
  return (
    <div className="max-h-[460px] overflow-auto rounded-xl border border-border/70 bg-black/30">
      <table className="w-full text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c}
                scope="col"
                className="sticky top-0 z-10 border-b border-border bg-neutral-900 px-3 py-2.5 text-left text-xs font-semibold text-neutral-400"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const active = r === selectedRow;
            return (
              <tr
                key={i}
                tabIndex={0}
                onClick={() => onSelect(r)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(r);
                  }
                }}
                className={`cursor-pointer transition-colors duration-200 ${
                  active ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                }`}
              >
                {columns.map((c) => (
                  <td
                    key={c}
                    className={`border-b border-border/40 px-3 py-2.5 align-top ${
                      WRAP_COLS.has(c) ? "min-w-56 break-words" : "whitespace-nowrap"
                    } ${TONE[r[c]] || "text-neutral-200"}`}
                  >
                    {cell(r[c])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PhotoTile({ photo, ready, onOpen }) {
  const caption = (
    <>
      <span className="block truncate text-[11px] text-neutral-400">
        Claim {photo.claim || "—"}
      </span>
      <span className="block truncate text-[11px] text-neutral-600">
        {photo.date || "No claim date"}
      </span>
    </>
  );
  if (!ready) {
    return (
      <div className="overflow-hidden rounded-lg border border-dashed border-border/70 bg-black/20">
        <div className="grid aspect-square place-items-center px-2 text-center">
          <span className="text-[11px] leading-snug text-neutral-500">
            #{photo.pid}
            <br />
            not downloaded
          </span>
        </div>
        <div className="px-1.5 py-1.5">{caption}</div>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      title={`View photo #${photo.pid}`}
      aria-label={`View photo ${photo.pid}, claim ${photo.claim}, ${photo.side}`}
      className="group block w-full overflow-hidden rounded-lg border border-border/60 bg-black/40 text-left transition-colors duration-200 hover:border-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="relative block aspect-square overflow-hidden">
        <img
          src={`/api/photo/${photo.pid}/thumb`}
          alt={`Photo ${photo.pid}`}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
        />
        <span className="absolute left-1 top-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium leading-none text-neutral-100">
          {photo.side}
        </span>
        <span className="absolute bottom-1 left-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium leading-none text-neutral-100">
          #{photo.pid}
        </span>
      </span>
      <span className="block px-1.5 py-1.5">{caption}</span>
    </button>
  );
}

// Full-size photo with previous/next, opened from inside the employee panel.
function Lightbox({ photos, index, onClose, onIndex }) {
  const photo = photos[index];
  const many = photos.length > 1;
  const closeRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  // keep the latest props for the keyboard listener, so it is attached only once
  const latest = useRef({ index, count: photos.length, onClose, onIndex });
  latest.current = { index, count: photos.length, onClose, onIndex };

  useEffect(() => setLoaded(false), [index]);

  useEffect(() => {
    const onKey = (e) => {
      const cur = latest.current;
      if (e.key === "Escape") {
        e.preventDefault();
        cur.onClose();
      } else if (cur.count < 2) {
        return;
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        cur.onIndex((cur.index - 1 + cur.count) % cur.count);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        cur.onIndex((cur.index + 1) % cur.count);
      }
    };
    document.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, []);

  if (!photo) return null;

  const meta = [
    photo.side,
    photo.claim ? `Claim ${photo.claim}` : "",
    photo.date,
  ].filter(Boolean);
  const step = (d) => onIndex((index + d + photos.length) % photos.length);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Photo ${photo.pid}, ${index + 1} of ${photos.length}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 flex flex-col bg-black/90 px-3 py-3 sm:px-6 sm:py-5"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 text-sm text-neutral-400">
          <span className="font-medium text-neutral-100">Photo #{photo.pid}</span>
          <span className="tabular-nums">
            {" · "}
            {index + 1} of {photos.length}
          </span>
        </p>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close photo"
          className="grid size-9 shrink-0 place-items-center rounded-md border border-border/70 text-neutral-300 transition-colors duration-200 hover:border-neutral-500 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      <div className="relative mt-2 flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <img
          src={`/api/photo/${photo.pid}/thumb`}
          alt=""
          aria-hidden="true"
          className={`absolute max-h-full max-w-full object-contain transition-opacity duration-300 ${
            loaded ? "opacity-0" : "opacity-70"
          }`}
        />
        <img
          key={photo.pid}
          ref={(el) => {
            if (el?.complete && el.naturalWidth) setLoaded(true);
          }}
          src={`/api/photo/${photo.pid}`}
          alt={`Photo ${photo.pid}${photo.side ? `, ${photo.side}` : ""}`}
          onLoad={() => setLoaded(true)}
          className={`relative max-h-full max-w-full object-contain transition-opacity duration-300 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
        {!loaded && (
          <span className="absolute bottom-3 inline-flex items-center gap-2 rounded-full bg-black/70 px-2.5 py-1 text-xs text-neutral-300">
            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
            Loading photo
          </span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between gap-3">
        <p className="min-w-0 text-xs text-neutral-400">{meta.join(" · ")}</p>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => step(-1)}
            disabled={!many}
            aria-label="Previous photo"
            className="grid size-9 place-items-center rounded-md border border-border/70 text-neutral-300 transition-colors duration-200 hover:border-neutral-500 hover:text-foreground disabled:pointer-events-none disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => step(1)}
            disabled={!many}
            aria-label="Next photo"
            className="grid size-9 place-items-center rounded-md border border-border/70 text-neutral-300 transition-colors duration-200 hover:border-neutral-500 hover:text-foreground disabled:pointer-events-none disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}

function EmployeeDetail({ employee, flags, photos, photoFiles, onOpenPhoto, onClose, panelRef }) {
  const [view, setView] = useState("flags");
  // if the run carries no per-employee photo list, fall back to the photos named by the flags
  const fallbackPhotos = [
    ...new Set(
      flags
        .flatMap((f) => String(f["Photo #"] ?? "").match(/\d+/g) || [])
        .filter((n) => photoFiles[n]),
    ),
  ].map((n) => ({ pid: Number(n), claim: "", date: "", side: "" }));

  const openPhoto = (pid) => {
    const list = photos.length ? [...photos] : fallbackPhotos;
    let i = list.findIndex((p) => String(p.pid) === String(pid));
    if (i < 0) {
      list.push({ pid: Number(pid), claim: "", date: "", side: "" });
      i = list.length - 1;
    }
    onOpenPhoto(list, i);
  };

  const meta = [
    employee.Employee_code,
    employee.Designation,
    employee.HQ,
    employee.Zone,
    employee["L1 Approver"] ? `L1 approver ${employee["L1 Approver"]}` : "",
  ]
    .filter(Boolean)
    .map(cell);

  return (
    <div
      ref={panelRef}
      role="region"
      aria-label={`Details for ${cell(employee.User_Name) || cell(employee.Employee_code)}`}
      className="card-chai mt-4 p-4 sm:p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-display text-base font-semibold leading-snug sm:text-lg">
            {cell(employee.User_Name) || cell(employee.Employee_code)}
          </h3>
          <p className="mt-1 text-xs leading-relaxed text-neutral-500">{meta.join(" · ")}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close employee details"
          className="grid size-8 shrink-0 place-items-center rounded-md border border-border/60 text-neutral-400 transition-colors duration-200 hover:border-neutral-600 hover:text-foreground"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4">
        <div
          role="group"
          aria-label="What to show for this employee"
          className="inline-flex rounded-lg border border-border bg-black/40 p-1"
        >
          <button
            type="button"
            onClick={() => setView("flags")}
            aria-pressed={view === "flags"}
            className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors duration-200 ${
              view === "flags"
                ? "bg-orange-900/40 text-orange-100"
                : "text-neutral-400 hover:text-foreground"
            }`}
          >
            Red flags
            <span className="tabular-nums opacity-60">{flags.length}</span>
          </button>
          <button
            type="button"
            onClick={() => setView("photos")}
            aria-pressed={view === "photos"}
            className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors duration-200 ${
              view === "photos"
                ? "bg-orange-900/40 text-orange-100"
                : "text-neutral-400 hover:text-foreground"
            }`}
          >
            All photos
            <span className="tabular-nums opacity-60">{photos.length}</span>
          </button>
        </div>
        {view === "photos" && photos.length > 0 && (
          <span className="text-xs text-neutral-500">Click a photo to open it full size</span>
        )}
      </div>

      {view === "photos" &&
        (photos.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-400">No photos for this employee in this report.</p>
        ) : (
          <ul className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5">
            {photos.map((p) => (
              <li key={p.pid}>
                <PhotoTile
                  photo={p}
                  ready={Boolean(photoFiles[p.pid])}
                  onOpen={() => openPhoto(p.pid)}
                />
              </li>
            ))}
          </ul>
        ))}

      {view === "flags" && flags.length === 0 && (
        <p className="mt-3 text-sm text-neutral-400">No red flags for this employee.</p>
      )}

      {view === "flags" && flags.length > 0 && (
        <ul className="mt-3 space-y-2.5">
          {flags.map((f, i) => {
            const photoNums = String(f["Photo #"] ?? "").match(/\d+/g) || [];
            const thumbs = [...new Set(photoNums.filter((n) => photoFiles[n]))];
            const claim = f["Claim_Id(s)"] ? `Claim ${f["Claim_Id(s)"]}` : "";
            return (
              <li key={i} className="rounded-xl border border-border/60 bg-black/20 p-3">
                <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
                  <div className="min-w-0 flex-1 basis-64">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <span
                        className={`text-xs font-semibold ${TONE[f.Priority] || "text-neutral-400"}`}
                      >
                        {cell(f.Priority) || "Flag"}
                      </span>
                      <span className="text-xs text-neutral-500">
                        {photoNums.length > 0 && (
                          <>
                            Photo{" "}
                            {photoNums.map((n, idx) => (
                              <span key={`${n}-${idx}`}>
                                {idx > 0 ? ", " : ""}
                                {photoFiles[n] ? (
                                  <button
                                    type="button"
                                    onClick={() => openPhoto(n)}
                                    title="View the downloaded photo"
                                    aria-label={`View photo ${n}`}
                                    className="rounded-sm text-neutral-300 underline decoration-neutral-600 underline-offset-2 transition-colors duration-200 hover:text-foreground hover:decoration-neutral-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  >
                                    #{n}
                                  </button>
                                ) : (
                                  `#${n}`
                                )}
                              </span>
                            ))}
                          </>
                        )}
                        {photoNums.length > 0 && claim ? " · " : ""}
                        {claim}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-neutral-200">{cell(f.Category)}</p>
                    {f.Details && (
                      <p className="mt-1 text-xs leading-relaxed text-neutral-400">
                        {cell(f.Details)}
                      </p>
                    )}
                    {f["Suggested Action"] && (
                      <p className="mt-1.5 text-xs leading-relaxed text-yellow-300/90">
                        {cell(f["Suggested Action"])}
                      </p>
                    )}
                  </div>
                  {thumbs.length > 0 && (
                    <div className="flex shrink-0 flex-wrap gap-2">
                      {thumbs.map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => openPhoto(n)}
                          title={`View photo #${n}`}
                          aria-label={`View photo ${n}`}
                          className="group relative block h-[72px] w-[72px] overflow-hidden rounded-lg border border-border/60 bg-black/40 transition-colors duration-200 hover:border-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <img
                            src={`/api/photo/${n}/thumb`}
                            alt={`Photo ${n}`}
                            width="72"
                            height="72"
                            loading="lazy"
                            decoding="async"
                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
                          />
                          <span className="absolute bottom-1 left-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-medium leading-none text-neutral-100">
                            #{n}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Metric({ value, label, tone = "" }) {
  return (
    <div className="card-chai p-4 sm:opacity-90 sm:hover:opacity-100">
      <span className={`block text-2xl font-semibold tabular-nums ${tone}`}>{value ?? 0}</span>
      <span className="mt-1 block text-xs leading-snug text-neutral-400">{label}</span>
    </div>
  );
}

export default function Results({ result, tabs, onReset }) {
  const [tab, setTab] = useState("flags");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState(null); // { code, row } while an employee is open
  const [lightbox, setLightbox] = useState(null); // { photos, index } while a photo is open
  const panelRef = useRef(null);
  const r = result;

  const flags = tabs === null ? null : Array.isArray(tabs.red_flags) ? tabs.red_flags : [];
  const emps = tabs === null ? null : Array.isArray(tabs.employees) ? tabs.employees : [];

  const isFlags = tab === "flags";
  const rows = isFlags ? flags : emps;
  const columns = isFlags ? FLAG_COLS : EMP_COLS;
  const q = query.trim().toLowerCase();
  const visible =
    rows && q ? rows.filter((row) => columns.some((c) => cell(row[c]).toLowerCase().includes(q))) : rows;
  const saved = String(r.output || "").split(/[\\/]/).pop();

  const employee = detail ? (emps || []).find((e) => e.Employee_code === detail.code) || detail.row : null;
  const employeeFlags = detail ? (flags || []).filter((f) => f.Employee_code === detail.code) : [];
  const employeePhotos = detail ? (r.employee_photos || {})[detail.code] || [] : [];
  const photoFiles = r.photo_files || {};

  const selectRow = (row) => {
    const code = row.Employee_code;
    setDetail((d) => (d && d.code === code && d.row === row ? null : { code, row }));
  };

  // bring the opened panel into view, unless the OS asks for less motion
  useEffect(() => {
    if (!detail || !panelRef.current) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    panelRef.current.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
  }, [detail]);

  return (
    <section className="mt-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-2xl font-medium sm:text-[30px]">Results</h2>
          <p className="mt-1 break-all text-sm text-neutral-400">
            Finished in {r.minutes} min. Saved as <span className="text-neutral-300">{saved}</span>.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onReset}
            aria-label="Start fresh and reset the app"
            className="btn-asym inline-flex h-9 shrink-0 items-center gap-2 border border-border px-4 text-sm font-medium transition-colors duration-200 hover:bg-white/[0.06]"
            title="Clear this result and start the next audit"
          >
            Start fresh
            <RefreshCw className="size-3.5" aria-hidden="true" />
          </button>
          <a
            href="/api/report"
            className="btn-asym-mirror inline-flex h-9 shrink-0 items-center gap-2 border border-border px-4 text-sm font-medium transition-colors duration-200 hover:bg-white/[0.06]"
          >
            Download Excel
            <Download className="size-4" aria-hidden="true" />
          </a>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Metric value={r.photos} label="Photos" />
        <Metric value={r.claims} label="Claims" />
        <Metric
          value={r.non_compliant_photos}
          label="Photos without timestamp + location"
          tone="text-yellow-400"
        />
        <Metric value={r.high_flags} label="Photos with a high red flag" tone="text-red-400" />
        <Metric value={r.failed} label="Download failures" />
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-border bg-black/40 p-1">
          <button
            onClick={() => setTab("flags")}
            aria-pressed={isFlags}
            className={`inline-flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors duration-200 ${
              isFlags ? "bg-orange-900/40 text-orange-100" : "text-neutral-400 hover:text-foreground"
            }`}
          >
            Red flags
            <span className="text-xs tabular-nums opacity-60">{flags?.length ?? "…"}</span>
          </button>
          <button
            onClick={() => setTab("emps")}
            aria-pressed={!isFlags}
            className={`inline-flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors duration-200 ${
              !isFlags ? "bg-orange-900/40 text-orange-100" : "text-neutral-400 hover:text-foreground"
            }`}
          >
            Employees
            <span className="text-xs tabular-nums opacity-60">{emps?.length ?? "…"}</span>
          </button>
        </div>

        {rows && rows.length > 0 && (
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-neutral-500"
              aria-hidden="true"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={isFlags ? "Search red flags" : "Search employees"}
              aria-label="Search rows"
              className="h-9 w-full rounded-md border border-input bg-black/40 pl-9 pr-3 text-sm placeholder:text-neutral-500 focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        )}
      </div>

      <div className="mt-4">
        <Table
          rows={visible}
          columns={columns}
          query={q}
          onSelect={selectRow}
          selectedRow={detail?.row}
        />
        {visible && visible.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-500">
            <span>Click a row to see that employee&rsquo;s flags</span>
            <span className="tabular-nums">
              {q ? `${visible.length} of ${rows.length} rows` : `${rows.length} rows`}
            </span>
          </div>
        )}
      </div>

      {detail && employee && (
        <EmployeeDetail
          key={detail.code}
          employee={employee}
          flags={employeeFlags}
          photos={employeePhotos}
          photoFiles={photoFiles}
          onOpenPhoto={(photos, index) => setLightbox({ photos, index })}
          onClose={() => {
            setDetail(null);
            setLightbox(null);
          }}
          panelRef={panelRef}
        />
      )}

      {lightbox && (
        <Lightbox
          photos={lightbox.photos}
          index={lightbox.index}
          onClose={() => setLightbox(null)}
          onIndex={(index) => setLightbox((l) => ({ ...l, index }))}
        />
      )}

      <div className="card-chai mt-6 p-4 text-sm leading-relaxed text-neutral-400">
        <b className="font-semibold text-yellow-400">Before you send it:</b> open the Excel, filter
        the Photo Review column U, check the marked photos at full size and fill column V. Automatic
        reading is not perfect, see the README.
      </div>
    </section>
  );
}
