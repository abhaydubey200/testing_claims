import { useState } from "react";
import { ChevronDown } from "lucide-react";

const ASIDE =
  "border-b border-card-edge bg-black/20 px-5 py-5 backdrop-blur-sm lg:sticky lg:top-0 lg:h-screen lg:w-[300px] lg:shrink-0 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:px-6 lg:py-8";

function Group({ title, hint, children }) {
  return (
    <section className="mt-6 border-t border-border/60 pt-5 first:mt-5">
      <h4 className="text-sm font-semibold">{title}</h4>
      {hint && <p className="mt-1 text-xs leading-relaxed text-neutral-500">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Slider({ id, label, value, min, max, step, display, hint, onChange }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm text-neutral-300">
          {label}
        </label>
        <span className="rounded-md border border-border/70 px-2 py-0.5 text-xs font-medium tabular-nums text-neutral-200">
          {display ?? value}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
        className="range mt-2.5 w-full"
      />
      {hint && <p className="mt-1 text-xs leading-relaxed text-neutral-500">{hint}</p>}
    </div>
  );
}

function Rupee({ id, label, value, onChange }) {
  return (
    <label htmlFor={id} className="flex items-center justify-between gap-3">
      <span className="text-sm text-neutral-300">{label}</span>
      <span className="relative">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-neutral-500"
        >
          ₹
        </span>
        <input
          id={id}
          type="number"
          min="0"
          max="50"
          step="0.5"
          value={value}
          onChange={onChange}
          className="w-24 rounded-md border border-input bg-black/40 py-1.5 pl-6 pr-2 text-right text-sm tabular-nums transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </span>
    </label>
  );
}

export default function Sidebar({ settings, onChange }) {
  const [open, setOpen] = useState(false);

  if (!settings) {
    return (
      <aside className={ASIDE}>
        <h3 className="text-base font-medium">Settings</h3>
        <p className="mt-2 text-sm text-neutral-500">Loading…</p>
      </aside>
    );
  }

  const num = (key, e) => onChange({ [key]: e.target.value === "" ? 0 : Number(e.target.value) });

  const body = (
    <>
      <Group title="Performance">
        <Slider
          id="download-threads"
          label="Photos downloaded at once"
          value={settings.download_threads ?? 8}
          min={2}
          max={16}
          step={1}
          hint="Higher downloads finish sooner but use more bandwidth."
          onChange={(e) => num("download_threads", e)}
        />
        <div className="mt-5">
          <Slider
            id="ocr-workers"
            label="Photos read at once"
            value={settings.ocr_workers ?? 2}
            min={1}
            max={6}
            step={1}
            hint="Raise this on a fast PC."
            onChange={(e) => num("ocr_workers", e)}
          />
        </div>
      </Group>

      <Group
        title="Km check (optional)"
        hint="Used only when the Bizom km column is empty. Enter the amount paid per km; 0 turns it off."
      >
        <div className="space-y-2.5">
          <Rupee
            id="bike-rate"
            label="Bike ₹/km"
            value={settings.bike_rate ?? 0}
            onChange={(e) => num("bike_rate", e)}
          />
          <Rupee
            id="car-rate"
            label="Car ₹/km"
            value={settings.car_rate ?? 0}
            onChange={(e) => num("car_rate", e)}
          />
        </div>
      </Group>

      <Group title="AI mark">
        <Slider
          id="sparkle-score"
          label="Sparkle-mark sensitivity"
          value={settings.sparkle_score ?? 0.85}
          min={0.7}
          max={0.98}
          step={0.01}
          display={Number(settings.sparkle_score ?? 0.85).toFixed(2)}
          hint="Lower means more photos get flagged."
          onChange={(e) => num("sparkle_score", e)}
        />
      </Group>
    </>
  );

  return (
    <aside className={ASIDE}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="settings-body"
        className="flex w-full items-center justify-between gap-3 lg:hidden"
      >
        <span className="text-base font-medium">Settings</span>
        <span className="flex items-center gap-1.5 text-xs text-neutral-500">
          {open ? "Hide" : "Adjust"}
          <ChevronDown
            className={`size-4 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </span>
      </button>
      <h3 className="hidden text-base font-medium lg:block">Settings</h3>
      <p className="mt-1 hidden text-xs text-neutral-500 lg:block">Changes save on their own.</p>

      <div id="settings-body" className={`${open ? "block" : "hidden"} lg:block`}>
        {body}
        <p className="mt-6 border-t border-border/60 pt-4 text-xs leading-relaxed text-neutral-500">
          Settings apply to the next run.
        </p>
      </div>
    </aside>
  );
}
