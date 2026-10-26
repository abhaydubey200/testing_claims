import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Upload,
} from "lucide-react";
import { api, uploadFile } from "./api";
import Sidebar from "./components/Sidebar.jsx";
import Results from "./components/Results.jsx";
import Backdrop from "./components/Backdrop.jsx";

// The five stages of a run, with the slice of the progress bar each one covers.
const STAGES = [
  { key: "Reading claim file", label: "Reading the claim file", range: [0, 0.02] },
  { key: "Downloading photos", label: "Downloading the photos", range: [0.02, 0.25] },
  { key: "Reading photos", label: "Reading each photo", range: [0.25, 0.9] },
  { key: "Running fraud checks", label: "Running the fraud checks", range: [0.9, 0.93] },
  { key: "Writing Excel report", label: "Writing the Excel report", range: [0.93, 0.99] },
];
const RANGE = Object.fromEntries(STAGES.map((s) => [s.key, s.range]));

const EMPTY_PROG = {
  status: "idle",
  stage: "",
  done: 0,
  total: 0,
  error: "",
  traceback: "",
  result: null,
};

function pct(p) {
  const [a, b] = RANGE[p.stage] || [0, 1];
  return Math.min(1, a + (b - a) * (p.done / Math.max(p.total, 1)));
}

function formatSize(bytes) {
  if (typeof bytes !== "number") return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatElapsed(ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function StageRow({ state, label, count }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      <span
        aria-hidden="true"
        className={`grid size-5 shrink-0 place-items-center rounded-full border ${
          state === "done"
            ? "border-neutral-700 bg-neutral-800 text-neutral-300"
            : state === "active"
              ? "border-neutral-600 bg-transparent text-neutral-200"
              : "border-neutral-800 bg-transparent"
        }`}
      >
        {state === "done" ? (
          <Check className="size-3" />
        ) : state === "active" ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <span className="size-1.5 rounded-full bg-neutral-700" />
        )}
      </span>
      <span
        className={
          state === "todo"
            ? "text-neutral-500"
            : state === "active"
              ? "font-medium text-foreground"
              : "text-neutral-400"
        }
      >
        {label}
      </span>
      {count && (
        <span className="ml-auto whitespace-nowrap pl-3 text-xs tabular-nums text-neutral-500">
          {count}
        </span>
      )}
    </li>
  );
}

export default function App({ onReset }) {
  const [settings, setSettings] = useState(null);
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState("");
  const [prog, setProg] = useState(EMPTY_PROG);
  const [tabs, setTabs] = useState(null);
  const [notice, setNotice] = useState(null); // {kind: "ok" | "err", text}
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState(null);
  const [now, setNow] = useState(0);
  const skipPost = useRef(true);

  const loadFiles = useCallback(async () => {
    try {
      const f = await api("/api/files");
      setFiles(f);
      setSelected((cur) => (f.some((x) => x.name === cur) ? cur : f[0]?.name || ""));
      return f;
    } catch {
      return [];
    }
  }, []);

  // initial load: settings + files (an in-progress run arrives over SSE)
  useEffect(() => {
    (async () => {
      try {
        setSettings(await api("/api/settings"));
      } catch {
        setSettings({});
      }
      skipPost.current = false;
      await loadFiles();
    })();
  }, [loadFiles]);

  // save settings (debounced) whenever they change after the initial load
  useEffect(() => {
    if (!settings || skipPost.current) return;
    const t = setTimeout(() => {
      api("/api/settings", { method: "POST", body: settings }).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [settings]);

  // live progress via Server-Sent Events: one connection for the lifetime of the page;
  // the first message restores an already-running audit after a refresh.
  useEffect(() => {
    const es = new EventSource("/api/progress/stream");
    es.onmessage = (ev) => {
      try {
        const next = JSON.parse(ev.data);
        setProg((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
      } catch {
        /* ignore malformed event */
      }
    };
    return () => es.close();
  }, []);

  // fetch the report tabs when a run finishes
  useEffect(() => {
    if (prog.status === "done" && prog.result) {
      api("/api/tabs")
        .then(setTabs)
        .catch(() => setTabs(null));
    }
  }, [prog.status, prog.result]);

  // keep the run clock ticking, and clear it when the run ends
  useEffect(() => {
    if (!startedAt) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const changeSettings = (patch) => setSettings((s) => ({ ...(s || {}), ...patch }));

  const doUpload = async (file) => {
    if (!file) return;
    setBusy(true);
    setNotice(null);
    try {
      const r = await uploadFile(file);
      setNotice({ kind: "ok", text: `Saved ${r.name} to the data folder.` });
      await loadFiles();
      setSelected(r.name);
    } catch (e) {
      setNotice({ kind: "err", text: `Upload failed: ${e.message}` });
    }
    setBusy(false);
  };

  const runAudit = async () => {
    if (!selected) return;
    setBusy(true);
    setNotice(null);
    try {
      await api("/api/run", { method: "POST", body: { file: selected } });
      setTabs(null);
      setProg({ ...EMPTY_PROG, status: "running", stage: "Reading claim file" });
      setStartedAt(Date.now());
      setNow(Date.now());
    } catch (e) {
      setNotice({ kind: "err", text: e.message });
    }
    setBusy(false);
  };

  const handleReset = async () => {
    setBusy(true);
    setNotice(null);
    try {
      await api("/api/reset", { method: "POST" });
      setProg(EMPTY_PROG);
      setTabs(null);
      setStartedAt(null);
      setNow(0);
      setNotice({ kind: "ok", text: "App reset. Drop or choose a claim file to start the next audit." });
    } catch (e) {
      setNotice({ kind: "err", text: e.message });
    }
    setBusy(false);
  };

  const running = prog.status === "running";
  const percent = Math.round(pct(prog) * 100);
  const stageIndex = STAGES.findIndex((s) => s.key === prog.stage);

  return (
    <div className="relative isolate flex min-h-screen flex-col overflow-x-clip lg:flex-row">
      <Backdrop />
      <Sidebar settings={settings} onChange={changeSettings} />

      <main className="mx-auto w-full max-w-6xl min-w-0 px-5 py-10 sm:px-10 lg:py-14">
        <header className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-card-edge bg-black/20 px-3 py-1 text-xs text-neutral-400">
            <span className="size-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
            Runs on this computer · v{settings?.version || "1.0.0"}
          </span>
          <h1 className="mt-4 text-2xl font-medium tracking-tight sm:text-[32px]">
            Odometer photo audit
          </h1>
          <p className="mt-3 text-base leading-relaxed text-neutral-400 md:text-lg">
            Checks the start and end odometer photos in a Bizom claim extract and writes an Excel
            report of the <span className="highlight">suspicious claims</span>.
          </p>
        </header>

        {notice && (
          <div
            role={notice.kind === "ok" ? "status" : "alert"}
            className={`card-chai mx-auto mt-6 flex max-w-2xl items-start gap-3 px-4 py-3 text-sm ${
              notice.kind === "ok" ? "text-emerald-300" : "text-red-300"
            }`}
          >
            {notice.kind === "ok" ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            )}
            <span>{notice.text}</span>
          </div>
        )}

        {prog.status === "error" && (
          <div
            role="alert"
            className="card-chai mx-auto mt-6 max-w-2xl px-4 py-3 text-sm text-red-300"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>The run stopped: {prog.error}</span>
            </div>
            {prog.traceback && (
              <details className="mt-2 pl-7">
                <summary className="cursor-pointer text-xs text-red-300/70 hover:text-red-200">
                  Technical details
                </summary>
                <pre className="mt-2 max-h-60 overflow-auto rounded-md bg-black/40 p-3 text-xs leading-relaxed text-neutral-300">
                  {prog.traceback}
                </pre>
              </details>
            )}
          </div>
        )}

        <section className="card-chai mt-8 p-5 sm:p-7">
          <p className="text-xs font-medium text-neutral-500">Step 1 of 2</p>
          <h2 className="mt-1 font-display text-lg font-semibold leading-snug sm:text-xl">
            Choose the claim extract
          </h2>
          <p className="mt-1 text-sm text-neutral-400">
            A CSV or Excel file with the{" "}
            <span className="text-neutral-200">Odometer Image of Start / End</span> columns.
          </p>

          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              doUpload(e.dataTransfer.files?.[0]);
            }}
            className={`group mt-4 flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-7 text-center transition-colors duration-200 focus-within:border-neutral-500 ${
              drag
                ? "border-highlight/60 bg-white/[0.03]"
                : "border-border hover:border-neutral-600"
            }${busy ? " pointer-events-none opacity-60" : ""}`}
          >
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              className="sr-only"
              onChange={(e) => {
                doUpload(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <span className="grid size-10 place-items-center rounded-full border border-border bg-white/[0.02] transition-colors group-hover:border-neutral-600">
              <Upload className="size-4 text-neutral-300" aria-hidden="true" />
            </span>
            <span className="mt-1 text-sm font-medium text-foreground">
              Drop a claim extract here
            </span>
            <span className="-mt-1 text-xs text-neutral-500">
              or click to choose a .csv, .xlsx or .xls file
            </span>
          </label>

          {files.length > 0 && (
            <>
              <div className="mt-5 flex items-center gap-3">
                <span className="h-px flex-1 bg-border/70" aria-hidden="true" />
                <span className="text-xs text-neutral-500">in the data folder</span>
                <span className="h-px flex-1 bg-border/70" aria-hidden="true" />
              </div>

              <div
                role="radiogroup"
                aria-label="Claim file to audit"
                className="mt-3 max-h-64 divide-y divide-border/50 overflow-y-auto rounded-xl border border-border/70 bg-black/20"
              >
                {files.map((f) => {
                  const active = f.name === selected;
                  return (
                    <label
                      key={f.name}
                      className={`flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors duration-200 ${
                        active ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"
                      }`}
                    >
                      <input
                        type="radio"
                        name="claim-file"
                        value={f.name}
                        checked={active}
                        onChange={() => setSelected(f.name)}
                        className="peer sr-only"
                      />
                      <span
                        aria-hidden="true"
                        className={`grid size-4 shrink-0 place-items-center rounded-full border peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background ${
                          active ? "border-neutral-300" : "border-neutral-600"
                        }`}
                      >
                        {active && <span className="size-2 rounded-full bg-neutral-100" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm text-neutral-100">{f.name}</span>
                        <span className="mt-0.5 block text-xs text-neutral-500">
                          {formatSize(f.size)} · added {f.added}
                        </span>
                      </span>
                      {active && <Check className="size-4 shrink-0 text-neutral-300" aria-hidden="true" />}
                    </label>
                  );
                })}
              </div>
            </>
          )}

          {files.length === 0 && (
            <div className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center">
              <p className="text-sm text-neutral-300">No claim file yet</p>
              <p className="mt-1 text-xs text-neutral-500">
                Drop one above, or copy it into the data folder next to the app.
              </p>
            </div>
          )}
        </section>

        <section className="card-chai mt-5 p-5 sm:p-7">
          <p className="text-xs font-medium text-neutral-500">Step 2 of 2</p>
          <h2 className="mt-1 font-display text-lg font-semibold leading-snug sm:text-xl">
            Run the audit
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-neutral-400">
            Downloads both photo columns, reads every photo, runs the fraud checks and builds the
            Excel report.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3">
            <button
              onClick={runAudit}
              disabled={busy || running || !selected}
              className="btn-asym inline-flex h-9 items-center gap-2 bg-neutral-100 px-4 text-sm font-medium text-neutral-900 transition-colors duration-200 hover:bg-white disabled:pointer-events-none disabled:opacity-40"
            >
              {running ? "Running…" : "Run audit"}
              {running ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <ArrowUpRight className="size-4" aria-hidden="true" />
              )}
            </button>
            <p className="min-w-0 text-xs text-neutral-500">
              {selected ? (
                <>
                  Audits <span className="break-all text-neutral-300">{selected}</span>
                </>
              ) : (
                "Choose a file first."
              )}
            </p>
          </div>

          {running && (
            <div className="mt-5 rounded-xl border border-border/70 bg-black/20 p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <span className="text-sm font-medium">
                  {STAGES[stageIndex]?.label || "Starting"}…
                </span>
                <span className="text-xs tabular-nums text-neutral-400">
                  {percent}%{startedAt ? ` · ${formatElapsed(now - startedAt)}` : ""}
                </span>
              </div>
              <div
                className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-neutral-800"
                role="progressbar"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Audit progress"
              >
                <div
                  className="h-full rounded-full bg-neutral-200 transition-[width] duration-500 ease-out"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <ol className="mt-4 grid gap-x-8 gap-y-2 sm:grid-cols-2">
                {STAGES.map((s, i) => {
                  const state = i < stageIndex ? "done" : i === stageIndex ? "active" : "todo";
                  return (
                    <StageRow
                      key={s.key}
                      state={state}
                      label={s.label}
                      count={
                        state === "active" && prog.total > 1
                          ? `${prog.done}/${prog.total}`
                          : null
                      }
                    />
                  );
                })}
              </ol>
            </div>
          )}
        </section>

        {prog.status === "done" && prog.result && <Results result={prog.result} tabs={tabs} onReset={handleReset} />}
      </main>
    </div>
  );
}
