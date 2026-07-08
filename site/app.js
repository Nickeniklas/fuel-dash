/* Helsinki fuel dashboard. Reads only site/data/*.json (see docs/PLAN.md). */
"use strict";

const FUELS = ["95", "98", "dsl"];
const FUEL_LABELS = { "95": "95E10", "98": "98E5", "dsl": "Diesel" };
// Color follows the fuel, never the series count — fixed slots in both views.
const FUEL_COLOR_VARS = { "95": "--fuel-95", "98": "--fuel-98", "dsl": "--fuel-dsl" };

const state = {
  fuel: "95",
  meta: null,
  current: null,
  median: null,
  combinedSeries: null, // cache when series_mode === "combined"
  charts: { station: null, median: null },
  rendered: { station: false, median: false },
};

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fuelColor = (fuel) => cssVar(FUEL_COLOR_VARS[fuel]);

async function fetchJSON(path) {
  const resp = await fetch(path, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`);
  return resp.json();
}

// Tiny series-loading helper: keeps the dashboard agnostic to the export's
// combined-vs-per-station file decision (driven by meta.json).
async function loadSeries(stationId) {
  if (state.meta.series_mode === "combined") {
    state.combinedSeries ??= await fetchJSON("data/series.json");
    return state.combinedSeries[stationId] || {};
  }
  return fetchJSON(`data/stations/${stationId}.json`);
}

function relTime(iso) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (!Number.isFinite(mins)) return "?";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 48 * 60) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}

/* ---- current price table ---- */

function renderTable() {
  const tbody = document.querySelector("#price-table tbody");
  const rows = state.current.stations
    .filter((s) => s.prices[state.fuel])
    .sort((a, b) => a.prices[state.fuel].price - b.prices[state.fuel].price);

  tbody.replaceChildren(...rows.map((s, i) => {
    const p = s.prices[state.fuel];
    const tr = document.createElement("tr");

    const deltaTd = document.createElement("td");
    deltaTd.className = "num";
    if (p.avg7d) {
      const pct = ((p.price - p.avg7d) / p.avg7d) * 100;
      // ±0.25 % of the station's own 7-day average counts as "flat"
      const cls = pct < -0.25 ? "delta-good" : pct > 0.25 ? "delta-bad" : "delta-flat";
      const arrow = pct < -0.25 ? "▼" : pct > 0.25 ? "▲" : "≈";
      deltaTd.innerHTML = `<span class="${cls}">${arrow} ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%</span>`;
    } else {
      deltaTd.textContent = "—";
    }

    const cells = [
      Object.assign(document.createElement("td"), { textContent: String(i + 1) }),
      (() => {
        const td = document.createElement("td");
        const sub = [s.brand, [s.street, s.city].filter(Boolean).join(", ")].filter(Boolean).join(" · ");
        td.innerHTML = `${s.name}<br><span class="station-sub"></span>`;
        td.querySelector(".station-sub").textContent = sub;
        return td;
      })(),
      Object.assign(document.createElement("td"), { className: "num", textContent: p.price.toFixed(3) }),
      deltaTd,
      Object.assign(document.createElement("td"), { textContent: relTime(p.updated) }),
    ];
    tr.replaceChildren(...cells);
    return tr;
  }));
}

/* ---- charts ---- */

function baseChartOptions() {
  const grid = cssVar("--grid");
  const muted = cssVar("--muted");
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { labels: { color: cssVar("--ink-2"), usePointStyle: true, pointStyleWidth: 10 } },
      tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y?.toFixed(3)} €/l` } },
    },
    scales: {
      x: { type: "time", grid: { color: grid }, ticks: { color: muted }, border: { color: cssVar("--border")} },
      y: { grid: { color: grid }, ticks: { color: muted, callback: (v) => v.toFixed(2) }, border: { color: cssVar("--border") },
           title: { display: true, text: "€/l", color: muted } },
    },
  };
}

function lineDataset(fuel, data) {
  return {
    label: FUEL_LABELS[fuel],
    data,
    borderColor: fuelColor(fuel),
    backgroundColor: fuelColor(fuel),
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 5,
    spanGaps: true,
  };
}

async function renderStationChart() {
  const stationId = document.getElementById("station-picker").value;
  if (!stationId) return;
  const series = await loadSeries(stationId);
  const datasets = FUELS.filter((f) => series[f]?.length).map((f) =>
    lineDataset(f, series[f].map(([t, price]) => ({ x: t, y: price }))),
  );
  state.charts.station?.destroy();
  state.charts.station = new Chart(document.getElementById("station-chart"), {
    type: "line",
    data: { datasets },
    options: baseChartOptions(),
  });
}

function renderMedianChart() {
  const m = state.median;
  const datasets = FUELS.map((f) =>
    lineDataset(f, m.dates.map((d, i) => ({ x: d, y: m[f][i] }))),
  );
  state.charts.median?.destroy();
  state.charts.median = new Chart(document.getElementById("median-chart"), {
    type: "line",
    data: { datasets },
    options: baseChartOptions(),
  });
}

/* ---- wiring ---- */

function showView(view) {
  document.querySelectorAll(".view").forEach((el) => (el.hidden = el.id !== `view-${view}`));
  document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  // Charts render lazily on first visit so the canvas has real dimensions.
  if (view === "station" && !state.rendered.station) { state.rendered.station = true; renderStationChart(); }
  if (view === "median" && !state.rendered.median) { state.rendered.median = true; renderMedianChart(); }
}

function populatePicker() {
  const picker = document.getElementById("station-picker");
  const stations = [...state.current.stations].sort((a, b) => a.name.localeCompare(b.name, "fi"));
  picker.replaceChildren(...stations.map((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.city ? `${s.name} (${s.city})` : s.name;
    return opt;
  }));
  picker.addEventListener("change", renderStationChart);
}

async function init() {
  [state.meta, state.current, state.median] = await Promise.all([
    fetchJSON("data/meta.json"), fetchJSON("data/current.json"), fetchJSON("data/median.json"),
  ]);

  document.getElementById("meta-line").textContent =
    `${state.meta.station_count} stations within ${(state.meta.radius_m / 1000).toFixed(0)} km of Helsinki center · last poll ${relTime(state.meta.last_poll)}`;

  renderTable();
  populatePicker();

  document.getElementById("fuel-toggle").addEventListener("click", (e) => {
    const fuel = e.target.dataset?.fuel;
    if (!fuel) return;
    state.fuel = fuel;
    document.querySelectorAll("#fuel-toggle button").forEach((b) => b.classList.toggle("active", b.dataset.fuel === fuel));
    renderTable();
  });

  document.getElementById("tabs").addEventListener("click", (e) => {
    if (e.target.dataset?.view) { location.hash = e.target.dataset.view; showView(e.target.dataset.view); }
  });

  // Deep-link support: #current / #station / #median
  const hash = location.hash.slice(1);
  if (["station", "median"].includes(hash)) showView(hash);

  // Re-theme charts when the OS color scheme flips.
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (state.rendered.station) renderStationChart();
    if (state.rendered.median) renderMedianChart();
  });
}

init().catch((e) => {
  document.getElementById("meta-line").textContent = `failed to load data: ${e.message}`;
});
