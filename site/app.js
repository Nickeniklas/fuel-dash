'use strict';

// ---- Config (tunables) ----
const HELSINKI_CENTER = [60.1699, 24.9384];
const RADIUS_KM = 15;
const AVG_WINDOW_DAYS = 7;
const STALE_DAYS = 2;
const SOURCE_WINDOW_DAYS = 5;
const COLOR_EPSILON = 0.005;
const MIN_TREND_POINTS = 3;

const FUEL_ORDER = ['95', '98', 'dsl'];
const FUEL_LABELS = { '95': '95E10', '98': '98E', dsl: 'Diesel' };

// Mirrors the :root custom properties in style.css.
const COLORS = {
  text: '#e8eaed',
  muted: '#9aa1ac',
  green: '#3ecf7e',
  red: '#e5534b',
  neutral: '#9aa1ac',
  gridline: 'rgba(255,255,255,0.1)',
};

const FUEL_LINE_COLORS = { '95': '#4a9eff', '98': '#f6ad55', dsl: '#b794f4' };

const FAVORITES_STORAGE_KEY = 'fuel-dash:favorites';

// ---- State ----
const state = {
  fuel: '95',
  radiusMode: '15km', // '15km' | 'all'
  stations: [],
  history: {},
  medians: [],
  stationsById: new Map(),
  referenceDate: null,
  map: null,
  markersLayer: null,
  radiusCircle: null,
  trendChart: null,
  medianChart: null,
  favorites: new Set(),
  searchQuery: '',
  selectedStationId: null,
  sortKey: 'price',
  sortDir: 'asc',
};

// ---- Utilities ----
function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function parseISO(dateStr) {
  return new Date(dateStr + 'T00:00:00Z').getTime();
}

function daysBefore(referenceDate, dateStr) {
  return (parseISO(referenceDate) - parseISO(dateStr)) / 86400000;
}

function computeMedian(values) {
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function computeReferenceDate(medians) {
  if (!medians.length) return new Date().toISOString().slice(0, 10);
  return medians[medians.length - 1].date;
}

function computeStationAvg(stationId, fuel) {
  const hist = state.history[stationId] || [];
  const pts = hist.filter((e) => {
    if (e[fuel] == null) return false;
    const diff = daysBefore(state.referenceDate, e.date);
    return diff >= 0 && diff <= AVG_WINDOW_DAYS;
  });
  if (pts.length < 2) return null;
  const sum = pts.reduce((s, e) => s + e[fuel], 0);
  return sum / pts.length;
}

function computeStationPointCount(stationId, fuel) {
  const hist = state.history[stationId] || [];
  return hist.filter((e) => e[fuel] != null).length;
}

function stationStaleness(dateStr) {
  const diff = daysBefore(state.referenceDate, dateStr);
  if (diff > SOURCE_WINDOW_DAYS) return 'abandoned';
  if (diff > STALE_DAYS) return 'stale';
  return 'fresh';
}

// ---- Sorting ----
function sortValue(station, key) {
  const latest = station.latest[state.fuel];
  switch (key) {
    case 'name':
      return station.name;
    case 'price':
      return latest.price;
    case 'date':
      return parseISO(latest.date);
    case 'delta': {
      const avg = computeStationAvg(station.station_id, state.fuel);
      return avg == null ? null : latest.price - avg;
    }
    default:
      return null;
  }
}

function compareStations(a, b, key, dir) {
  const va = sortValue(a, key);
  const vb = sortValue(b, key);
  // Null averages always sort last, regardless of direction.
  if (va == null || vb == null) {
    if (va == null && vb == null) return 0;
    return va == null ? 1 : -1;
  }
  const mul = dir === 'asc' ? 1 : -1;
  if (typeof va === 'string') return mul * va.localeCompare(vb);
  return mul * (va - vb);
}

function sortStations(list) {
  return list.slice().sort((a, b) => compareStations(a, b, state.sortKey, state.sortDir));
}

// ---- Favorites ----
function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAVORITES_STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((id) => Number.isFinite(id)).map(Number));
  } catch {
    return new Set();
  }
}

function saveFavorites() {
  localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(Array.from(state.favorites)));
}

function pruneFavorites() {
  let changed = false;
  for (const id of Array.from(state.favorites)) {
    if (!state.stationsById.has(id)) {
      state.favorites.delete(id);
      changed = true;
    }
  }
  if (changed) saveFavorites();
}

function toggleFavorite(stationId) {
  if (state.favorites.has(stationId)) state.favorites.delete(stationId);
  else state.favorites.add(stationId);
  saveFavorites();
  renderTable();
  renderFavoriteChips();
}

// ---- Filtering ----
function stationHasFuel(station, fuel) {
  return station.latest && station.latest[fuel] != null;
}

function inRadius(station) {
  if (station.lat == null || station.lon == null) return false;
  return (
    haversineKm(HELSINKI_CENTER[0], HELSINKI_CENTER[1], station.lat, station.lon) <= RADIUS_KM
  );
}

function baseFilteredStations() {
  return state.stations.filter((s) => {
    if (!stationHasFuel(s, state.fuel)) return false;
    if (state.radiusMode === '15km') return inRadius(s);
    return true;
  });
}

function getMapStations() {
  return baseFilteredStations().filter((s) => s.lat != null && s.lon != null);
}

function matchesSearch(station) {
  if (!state.searchQuery) return true;
  return station.name.toLowerCase().includes(state.searchQuery);
}

function getPinnedStations() {
  return sortStations(
    state.stations.filter((s) => state.favorites.has(s.station_id) && stationHasFuel(s, state.fuel))
  );
}

function getMainTableStations() {
  return sortStations(
    baseFilteredStations().filter((s) => !state.favorites.has(s.station_id) && matchesSearch(s))
  );
}

// ---- Table ----
function createStationRow(station, { outsideArea }) {
  const latest = station.latest[state.fuel];
  const avg = computeStationAvg(station.station_id, state.fuel);
  const staleness = stationStaleness(latest.date);
  const isFavorite = state.favorites.has(station.station_id);

  const tr = document.createElement('tr');
  tr.className = 'station-row';
  if (staleness === 'stale') tr.classList.add('stale');
  else if (staleness === 'abandoned') tr.classList.add('abandoned');

  const tdStar = document.createElement('td');
  tdStar.className = 'star-cell';
  const starBtn = document.createElement('button');
  starBtn.type = 'button';
  starBtn.className = 'star-btn' + (isFavorite ? ' active' : '');
  starBtn.setAttribute('aria-pressed', String(isFavorite));
  starBtn.setAttribute(
    'aria-label',
    (isFavorite ? 'Remove ' : 'Add ') + station.name + (isFavorite ? ' from favorites' : ' to favorites')
  );
  starBtn.textContent = isFavorite ? '★' : '☆';
  starBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleFavorite(station.station_id);
  });
  tdStar.appendChild(starBtn);

  const tdName = document.createElement('td');
  tdName.className = 'station-name';
  tdName.textContent = station.name;
  if (outsideArea) {
    const hint = document.createElement('span');
    hint.className = 'outside-hint';
    hint.textContent = ' (outside area)';
    tdName.appendChild(hint);
  }

  const tdPrice = document.createElement('td');
  tdPrice.textContent = latest.price.toFixed(3) + ' €';

  const tdDate = document.createElement('td');
  tdDate.textContent = latest.date;
  if (staleness === 'abandoned') {
    const marker = document.createElement('span');
    marker.className = 'abandoned-marker';
    marker.textContent = '●';
    marker.title = `Not seen on the source in over ${SOURCE_WINDOW_DAYS} days`;
    tdDate.appendChild(marker);
  }

  const tdDelta = document.createElement('td');
  if (avg == null) {
    tdDelta.textContent = '—';
    tdDelta.className = 'delta-neutral';
  } else {
    const cents = (latest.price - avg) * 100;
    const sign = cents > 0 ? '+' : '';
    tdDelta.textContent = `${sign}${cents.toFixed(1)} c`;
    if (latest.price <= avg - COLOR_EPSILON) tdDelta.className = 'delta-green';
    else if (latest.price >= avg + COLOR_EPSILON) tdDelta.className = 'delta-red';
    else tdDelta.className = 'delta-neutral';
  }

  tr.append(tdStar, tdName, tdPrice, tdDate, tdDelta);
  tr.addEventListener('click', () => selectStation(station.station_id, { scroll: true }));
  return tr;
}

function updateSortHeaders() {
  document.querySelectorAll('#price-table th.sortable').forEach((th) => {
    const key = th.dataset.sortKey;
    const arrow = th.querySelector('.sort-arrow');
    if (key === state.sortKey) {
      th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
      arrow.textContent = state.sortDir === 'asc' ? '↑' : '↓';
    } else {
      th.setAttribute('aria-sort', 'none');
      arrow.textContent = '';
    }
  });
}

function setSort(key) {
  if (state.sortKey === key) {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    state.sortKey = key;
    state.sortDir = 'asc';
  }
  renderTable();
}

function initSortHeaders() {
  document.querySelectorAll('#price-table th.sortable').forEach((th) => {
    const btn = th.querySelector('.sort-btn');
    btn.addEventListener('click', () => setSort(th.dataset.sortKey));
  });
}

function renderTable() {
  updateSortHeaders();

  const pinned = getPinnedStations();
  const main = getMainTableStations();

  const tbody = document.getElementById('price-table-body');
  const emptyNote = document.getElementById('table-empty');
  tbody.innerHTML = '';

  if (!pinned.length && !main.length) {
    emptyNote.hidden = false;
    return;
  }
  emptyNote.hidden = true;

  for (const s of pinned) {
    const outsideArea = state.radiusMode === '15km' && !inRadius(s);
    tbody.appendChild(createStationRow(s, { outsideArea }));
  }

  if (pinned.length && main.length) {
    const divider = document.createElement('tr');
    divider.className = 'pinned-divider';
    const td = document.createElement('td');
    td.colSpan = 5;
    divider.appendChild(td);
    tbody.appendChild(divider);
  }

  for (const s of main) {
    tbody.appendChild(createStationRow(s, { outsideArea: false }));
  }
}

// ---- Map ----
function initMap() {
  state.map = L.map('map', { scrollWheelZoom: false }).setView(HELSINKI_CENTER, 10);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
    maxZoom: 19,
  }).addTo(state.map);
  state.markersLayer = L.layerGroup().addTo(state.map);

  state.map.getContainer().addEventListener('click', (e) => {
    const btn = e.target.closest('.popup-trend-btn');
    if (!btn) return;
    const id = Number(btn.dataset.stationId);
    if (Number.isFinite(id)) selectStation(id, { scroll: true });
  });
}

function buildPopupHtml(station) {
  const rows = FUEL_ORDER.map((f) => {
    const entry = station.latest[f];
    const label = FUEL_LABELS[f];
    if (!entry) return `<div>${label}: –</div>`;
    return `<div>${label}: ${entry.price.toFixed(3)} € (${entry.date})</div>`;
  }).join('');

  const latest = station.latest[state.fuel];
  const avg = computeStationAvg(station.station_id, state.fuel);
  let deltaHtml = `<div>vs 7d avg (${FUEL_LABELS[state.fuel]}): —</div>`;
  if (avg != null && latest) {
    const cents = (latest.price - avg) * 100;
    const sign = cents > 0 ? '+' : '';
    deltaHtml = `<div>vs 7d avg (${FUEL_LABELS[state.fuel]}): ${sign}${cents.toFixed(1)} c</div>`;
  }

  const trendBtn = `<button type="button" class="popup-trend-btn" data-station-id="${station.station_id}">View trend &rarr;</button>`;

  return `<b>${escapeHtml(station.name)}</b>${rows}${deltaHtml}${trendBtn}`;
}

function renderMap() {
  state.markersLayer.clearLayers();
  if (state.radiusCircle) {
    state.map.removeLayer(state.radiusCircle);
    state.radiusCircle = null;
  }
  if (state.radiusMode === '15km') {
    state.radiusCircle = L.circle(HELSINKI_CENTER, {
      radius: RADIUS_KM * 1000,
      color: COLORS.muted,
      weight: 1,
      fillColor: COLORS.muted,
      fillOpacity: 0.05,
    }).addTo(state.map);
  }

  const stations = getMapStations();
  const median = computeMedian(stations.map((s) => s.latest[state.fuel].price));

  for (const s of stations) {
    const price = s.latest[state.fuel].price;
    let color = COLORS.neutral;
    if (median != null) {
      if (price <= median - COLOR_EPSILON) color = COLORS.green;
      else if (price >= median + COLOR_EPSILON) color = COLORS.red;
    }

    L.circleMarker([s.lat, s.lon], {
      radius: 7,
      color,
      fillColor: color,
      fillOpacity: 0.85,
      weight: 1,
    })
      .bindPopup(buildPopupHtml(s))
      .addTo(state.markersLayer);
  }
}

// ---- Charts ----
function populateStationSelect() {
  const select = document.getElementById('station-select');
  const previousValue = state.selectedStationId || select.value;

  const options = Object.keys(state.history)
    .map((id) => ({
      id,
      name: (state.stationsById.get(Number(id)) || {}).name || `Station ${id}`,
      count: computeStationPointCount(id, state.fuel),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const rich = options.filter((o) => o.count >= MIN_TREND_POINTS);
  const sparse = options.filter((o) => o.count < MIN_TREND_POINTS);

  select.innerHTML = '';

  const appendGroup = (label, opts) => {
    if (!opts.length) return;
    const group = document.createElement('optgroup');
    group.label = label;
    for (const opt of opts) {
      const el = document.createElement('option');
      el.value = opt.id;
      el.textContent = `${opt.name} (${opt.count})`;
      group.appendChild(el);
    }
    select.appendChild(group);
  };

  appendGroup(`Frequently reported (${MIN_TREND_POINTS}+ points)`, rich);
  appendGroup('Rarely reported', sparse);

  if (previousValue && options.some((o) => o.id === previousValue)) {
    select.value = previousValue;
  } else if (rich.length) {
    select.value = rich[0].id;
  } else if (options.length) {
    select.value = options[0].id;
  }
}

function renderFavoriteChips() {
  const container = document.getElementById('favorite-chips');
  const stations = Array.from(state.favorites)
    .map((id) => state.stationsById.get(id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name));

  container.innerHTML = '';
  container.hidden = !stations.length;

  for (const station of stations) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'favorite-chip';
    if (String(station.station_id) === state.selectedStationId) chip.classList.add('active');
    chip.textContent = station.name;
    chip.addEventListener('click', () => selectStation(station.station_id));
    container.appendChild(chip);
  }
}

function updateSparseNote() {
  const note = document.getElementById('trend-sparse-note');
  const id = state.selectedStationId;
  if (!id) {
    note.hidden = true;
    return;
  }
  const count = computeStationPointCount(id, state.fuel);
  if (count >= MIN_TREND_POINTS) {
    note.hidden = true;
    return;
  }
  const station = state.stationsById.get(Number(id));
  const name = station ? station.name : 'This station';
  const pointWord = count === 1 ? 'point' : 'points';
  note.textContent = `${name} is rarely reported for ${FUEL_LABELS[state.fuel]} (${count} ${pointWord}) — the trend below is limited.`;
  note.hidden = false;
}

function selectStation(stationId, { scroll = false } = {}) {
  const id = String(stationId);
  if (!state.history[id]) return;

  state.selectedStationId = id;
  renderTrendChart(id);

  const select = document.getElementById('station-select');
  if (select.value !== id) select.value = id;

  renderFavoriteChips();
  updateSparseNote();

  if (scroll) {
    document.getElementById('trend-heading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function fuelDatasets(entries) {
  return FUEL_ORDER.map((f) => ({
    label: FUEL_LABELS[f],
    data: entries.map((e) => (e[f] != null ? e[f] : null)),
    borderColor: FUEL_LINE_COLORS[f],
    backgroundColor: FUEL_LINE_COLORS[f],
    spanGaps: true,
    tension: 0.15,
    pointRadius: 3,
  }));
}

function renderTrendChart(stationId) {
  const hist = state.history[stationId] || [];
  const labels = hist.map((e) => e.date);
  const datasets = fuelDatasets(hist);

  if (state.trendChart) {
    state.trendChart.data.labels = labels;
    state.trendChart.data.datasets = datasets;
    state.trendChart.update();
    return;
  }

  const ctx = document.getElementById('trend-chart').getContext('2d');
  state.trendChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { type: 'category' }, y: { beginAtZero: false } },
    },
  });
}

function renderMedianChart() {
  const labels = state.medians.map((e) => e.date);
  const datasets = fuelDatasets(state.medians);

  const ctx = document.getElementById('median-chart').getContext('2d');
  state.medianChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { type: 'category' }, y: { beginAtZero: false } },
    },
  });
}

// ---- Controls ----
function setupControls() {
  document.querySelectorAll('.fuel-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.fuel-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.fuel = btn.dataset.fuel;
      renderTable();
      renderMap();
      populateStationSelect();
      updateSparseNote();
    });
  });

  document.querySelectorAll('.radius-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.radius-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.radiusMode = btn.dataset.radius;
      renderTable();
      renderMap();
    });
  });

  document.getElementById('station-select').addEventListener('change', (e) => {
    selectStation(e.target.value);
  });

  const searchInput = document.getElementById('station-search');
  const searchClear = document.getElementById('station-search-clear');
  searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.trim().toLowerCase();
    searchClear.hidden = !state.searchQuery;
    renderTable();
  });
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    state.searchQuery = '';
    searchClear.hidden = true;
    renderTable();
    searchInput.focus();
  });
}

// ---- Data loading ----
function showError(message) {
  const el = document.getElementById('error-banner');
  el.textContent = message;
  el.hidden = false;
}

async function fetchJson(path, v) {
  const res = await fetch(`${path}?v=${v}`);
  if (!res.ok) throw new Error(`${path} returned HTTP ${res.status}`);
  return res.json();
}

async function loadData() {
  const v = Date.now();
  const [stations, history, medians] = await Promise.all([
    fetchJson('data/stations.json', v),
    fetchJson('data/history.json', v),
    fetchJson('data/medians.json', v),
  ]);
  return { stations, history, medians };
}

// ---- Bootstrap ----
async function main() {
  Chart.defaults.color = COLORS.text;
  Chart.defaults.borderColor = COLORS.gridline;

  try {
    const { stations, history, medians } = await loadData();
    state.stations = stations;
    state.history = history;
    state.medians = medians;
    state.stationsById = new Map(stations.map((s) => [s.station_id, s]));
    state.referenceDate = computeReferenceDate(medians);
  } catch (err) {
    showError('Failed to load fuel price data: ' + err.message);
    return;
  }

  state.favorites = loadFavorites();
  pruneFavorites();

  initMap();
  initSortHeaders();
  renderTable();
  renderMap();
  populateStationSelect();

  const select = document.getElementById('station-select');
  if (select.value) selectStation(select.value);

  renderMedianChart();
  renderFavoriteChips();
  setupControls();
}

main();
