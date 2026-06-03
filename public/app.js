/**
 * GHstar SPA — app.js
 * Vanilla JS, no framework, no build step.
 * Consumes: ./data/site/index.json, ./data/site/corpus.json,
 *           ./data/site/snapshots/<date>.json
 * Fallback:  ../fixtures/site-sample/ for local dev without built data.
 */

'use strict';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const DATA_BASE   = './data/site';
const FIX_BASE    = '../fixtures/site-sample';
const PAGE_SIZE   = 200;          // cards visible before "show more"

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  manifest:   null,   // parsed index.json
  corpus:     null,   // array from corpus.json
  snapshot:   null,   // array from snapshots/<date>.json (null = corpus mode)
  activeDate: 'all',
  filters: {
    category:    [],
    subcategory: [],
    language:    [],
    action_level: [],
    keyword:     '',
    sort:        'momentum_score',
  },
  visibleCount: PAGE_SIZE,
  filtered:   [],     // current filtered+sorted result
};

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const $ = id => document.getElementById(id);
const elBuildTime   = $('build-time');
const elFDate       = $('f-date');
const elFCat        = $('f-category');
const elFSub        = $('f-subcategory');
const elFLang       = $('f-language');
const elFAction     = $('f-action-level');
const elFKeyword    = $('f-keyword');
const elFSort       = $('f-sort');
const elBtnReset    = $('btn-reset');
const elTrendsBody  = $('trends-body');
const elTrendsSub   = $('trends-subtitle');
const elCount       = $('results-count');
const elCardList    = $('card-list');
const elShowMoreRow = $('show-more-row');
const elBtnMore     = $('btn-show-more');
const elLoading     = $('loading');
const elError       = $('error-msg');

// ---------------------------------------------------------------------------
// Fetch helpers with fixture fallback
// ---------------------------------------------------------------------------
async function fetchJSON(primaryUrl, fallbackUrl) {
  for (const url of [primaryUrl, fallbackUrl].filter(Boolean)) {
    try {
      const res = await fetch(url);
      if (res.ok) return res.json();
    } catch (_) { /* try next */ }
  }
  throw new Error(`Could not load data from ${primaryUrl} or fallback.`);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
async function init() {
  try {
    elLoading.hidden = false;
    elError.hidden   = true;

    // Load manifest first
    state.manifest = await fetchJSON(
      `${DATA_BASE}/index.json`,
      `${FIX_BASE}/index.json`
    );

    // Load corpus (default dataset)
    state.corpus = await fetchJSON(
      `${DATA_BASE}/corpus.json`,
      `${FIX_BASE}/corpus.json`
    );

    buildUI();
    elLoading.hidden = true;
    applyFilters();
  } catch (err) {
    elLoading.hidden = true;
    showError(err.message);
  }
}

// ---------------------------------------------------------------------------
// Build filter-bar options from manifest facets
// ---------------------------------------------------------------------------
function buildUI() {
  const m = state.manifest;

  // Build time
  if (m.build) {
    const d = new Date(m.build);
    elBuildTime.textContent = d.toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric'
    });
    elBuildTime.dateTime = m.build;
  }

  // Date picker: add "single date" options
  (m.dates || []).slice().reverse().forEach(date => {
    const opt = document.createElement('option');
    opt.value = date;
    opt.textContent = date;
    elFDate.appendChild(opt);
  });

  // Populate multi-selects from facets
  populateMultiSelect(elFCat,    m.facets.category    || {});
  populateMultiSelect(elFSub,    m.facets.subcategory || {});
  populateMultiSelect(elFLang,   m.facets.language    || {});
  populateMultiSelect(elFAction, m.facets.action_level|| {});

  // Wire events
  elFDate.addEventListener('change', onDateChange);
  elFCat.addEventListener('change',  () => onMultiChange('category',     elFCat));
  elFSub.addEventListener('change',  () => onMultiChange('subcategory',  elFSub));
  elFLang.addEventListener('change', () => onMultiChange('language',     elFLang));
  elFAction.addEventListener('change', () => onMultiChange('action_level', elFAction));
  elFKeyword.addEventListener('input', debounce(() => {
    state.filters.keyword = elFKeyword.value.trim().toLowerCase();
    state.visibleCount = PAGE_SIZE;
    applyFilters();
  }, 180));
  elFSort.addEventListener('change', () => {
    state.filters.sort = elFSort.value;
    state.visibleCount = PAGE_SIZE;
    applyFilters();
  });
  elBtnReset.addEventListener('click', resetFilters);
  elBtnMore.addEventListener('click', () => {
    state.visibleCount += PAGE_SIZE;
    renderCards();
  });
}

function populateMultiSelect(el, facet) {
  const sorted = Object.entries(facet).sort((a, b) => b[1] - a[1]);
  // Update size so dropdown shows up to 5 items without scroll
  el.size = Math.min(sorted.length + 1, 1); // keep as single for style; multi via Ctrl+click
  sorted.forEach(([val, count]) => {
    const opt = document.createElement('option');
    opt.value = val;
    opt.textContent = `${val} (${count})`;
    el.appendChild(opt);
  });
}

// ---------------------------------------------------------------------------
// Filter event handlers
// ---------------------------------------------------------------------------
async function onDateChange() {
  const val = elFDate.value;
  state.activeDate = val;
  state.visibleCount = PAGE_SIZE;

  if (val === 'all') {
    state.snapshot = null;
    applyFilters();
    return;
  }

  // Single date: load snapshot
  elLoading.hidden = false;
  try {
    state.snapshot = await fetchJSON(
      `${DATA_BASE}/snapshots/${val}.json`,
      `${FIX_BASE}/snapshots/${val}.json`
    );
  } catch (err) {
    showError(`Could not load snapshot for ${val}: ${err.message}`);
    state.snapshot = null;
  } finally {
    elLoading.hidden = true;
  }
  applyFilters();
}

function onMultiChange(key, el) {
  const selected = Array.from(el.selectedOptions)
    .map(o => o.value)
    .filter(v => v !== '');
  state.filters[key] = selected;
  state.visibleCount = PAGE_SIZE;
  applyFilters();
}

function resetFilters() {
  elFDate.value    = 'all';
  elFKeyword.value = '';
  elFSort.value    = 'momentum_score';
  [elFCat, elFSub, elFLang, elFAction].forEach(el => {
    Array.from(el.options).forEach(o => { o.selected = false; });
  });
  state.activeDate     = 'all';
  state.snapshot       = null;
  state.filters        = { category: [], subcategory: [], language: [], action_level: [], keyword: '', sort: 'momentum_score' };
  state.visibleCount   = PAGE_SIZE;
  applyFilters();
}

// ---------------------------------------------------------------------------
// Core filter + sort
// ---------------------------------------------------------------------------
function applyFilters() {
  const base   = state.snapshot || state.corpus || [];
  const f      = state.filters;
  const kw     = f.keyword;

  let results = base.filter(repo => {
    if (f.category.length    && !f.category.includes(repo.category))       return false;
    if (f.subcategory.length && !f.subcategory.includes(repo.subcategory)) return false;
    if (f.language.length    && !f.language.includes(repo.language))       return false;
    if (f.action_level.length && !f.action_level.includes(repo.action_level)) return false;
    if (kw) {
      const haystack = [
        repo.name        || '',
        repo.description || '',
        (repo.topics || []).join(' '),
      ].join(' ').toLowerCase();
      if (!haystack.includes(kw)) return false;
    }
    return true;
  });

  // Sort descending
  const sortKey = f.sort;
  results.sort((a, b) => (b[sortKey] || 0) - (a[sortKey] || 0));

  state.filtered = results;
  renderCount();
  renderTrends();
  renderCards();
}

// ---------------------------------------------------------------------------
// Render count
// ---------------------------------------------------------------------------
function renderCount() {
  const total = state.filtered.length;
  const src   = state.snapshot ? `snapshot ${state.activeDate}` : 'corpus';
  elCount.textContent = `${total.toLocaleString()} repo${total !== 1 ? 's' : ''} — ${src}`;
}

// ---------------------------------------------------------------------------
// Render trends panel
// ---------------------------------------------------------------------------
function renderTrends() {
  const repos  = state.filtered;
  if (!repos.length) {
    elTrendsBody.innerHTML = '<p style="color:var(--muted)">No data.</p>';
    elTrendsSub.textContent = '';
    return;
  }

  // Compute facet distributions from filtered set
  const counts = { category: {}, subcategory: {}, language: {}, action_level: {} };
  repos.forEach(r => {
    tally(counts.category,    r.category);
    tally(counts.subcategory, r.subcategory);
    tally(counts.language,    r.language);
    tally(counts.action_level, r.action_level);
  });

  elTrendsSub.textContent = `${repos.length} repos`;

  elTrendsBody.innerHTML = `
    <div class="spa-trends-grid">
      ${trendsSection('Categories',    counts.category)}
      ${trendsSection('Subcategories', counts.subcategory)}
      ${trendsSection('Languages',     counts.language)}
      ${trendsSection('Action Levels', counts.action_level)}
    </div>`;
}

function tally(obj, val) {
  if (!val) return;
  obj[val] = (obj[val] || 0) + 1;
}

function trendsSection(title, counts) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max     = entries[0] ? entries[0][1] : 1;
  const rows    = entries.slice(0, 8).map(([k, v]) => `
    <div class="score-row compact">
      <span>${esc(k)}</span>
      <b>${v}</b>
      <i style="width:${((v / max) * 100).toFixed(1)}%"></i>
    </div>`).join('');
  return `<div class="spa-trends-col">
    <h3>${esc(title)}</h3>
    <div class="score-chart">${rows}</div>
  </div>`;
}

// ---------------------------------------------------------------------------
// Render cards (paginated)
// ---------------------------------------------------------------------------
function renderCards() {
  const visible = state.filtered.slice(0, state.visibleCount);
  const total   = state.filtered.length;

  elCardList.innerHTML = visible.map(repoCard).join('');

  if (total > state.visibleCount) {
    elShowMoreRow.hidden = false;
    elBtnMore.textContent = `Show more (${total - state.visibleCount} remaining)`;
  } else {
    elShowMoreRow.hidden = true;
  }
}

// ---------------------------------------------------------------------------
// Card template
// ---------------------------------------------------------------------------
function repoCard(r) {
  const name     = esc(r.name || r.full_name || '');
  const owner    = esc(r.owner || '');
  const url      = esc(r.url  || `https://github.com/${r.full_name}`);
  const desc     = esc(r.description || '');
  const lang     = esc(r.language || '');
  const cat      = esc(r.category || '');
  const sub      = esc(r.subcategory || '');
  const stars    = num(r.stars);
  const spd      = r.stars_per_day != null ? r.stars_per_day.toFixed(1) : '—';
  const mom      = r.momentum_score != null ? r.momentum_score : '—';
  const str      = r.strategic_score != null ? r.strategic_score : '—';
  const action   = esc(r.action_level || '');
  const maturity = esc(r.maturity_level || '');
  const topics   = (r.topics || []).slice(0, 6)
    .map(t => `<span>${esc(t)}</span>`).join('');
  const risks    = (r.risk_flags || [])
    .map(f => `<span>${esc(f)}</span>`).join('');
  const spark    = sparkline(r.history || []);

  return `<article class="repo-card" role="listitem">
    <div class="repo-top">
      ${cat ? `<span class="category">${cat}</span>` : ''}
      ${sub ? `<span class="category" style="color:var(--accent-2)">${sub}</span>` : ''}
      ${action ? `<span class="stats span">${action}</span>` : ''}
      ${maturity ? `<span class="stats span" style="color:var(--muted)">${maturity}</span>` : ''}
    </div>
    <h3><a href="${url}" target="_blank" rel="noopener">${name}</a></h3>
    <p style="margin:0 0 10px;font-size:13px;color:var(--muted)">${owner}</p>
    ${desc ? `<p style="margin:0 0 12px;font-size:14px">${desc}</p>` : ''}
    <div class="stats">
      ${lang ? `<span>&#x1F4BB; ${lang}</span>` : ''}
      <span>&#x2605; ${stars}</span>
      <span>${spd}/day</span>
      <span style="color:var(--accent)">&#x26A1; ${mom}</span>
      <span style="color:var(--accent-2)">&#x1F3AF; ${str}</span>
    </div>
    ${spark ? `<div class="spa-spark-wrap">${spark}</div>` : ''}
    ${topics ? `<div class="topics" style="margin-top:10px">${topics}</div>` : ''}
    ${risks  ? `<div class="risks stats" style="margin-top:8px">${risks}</div>` : ''}
    <div class="bar" style="margin-top:12px"><i style="background:var(--accent);width:${mom !== '—' ? mom : 0}%"></i></div>
  </article>`;
}

// ---------------------------------------------------------------------------
// Sparkline (inline SVG from history[].stars)
// ---------------------------------------------------------------------------
function sparkline(history) {
  if (!history || history.length < 2) return '';
  const vals = history.map(h => h.stars || 0);
  const min  = Math.min(...vals);
  const max  = Math.max(...vals);
  const range = max - min || 1;
  const W = 120, H = 28, pad = 2;
  const step = (W - pad * 2) / (vals.length - 1);
  const pts  = vals.map((v, i) => {
    const x = pad + i * step;
    const y = H - pad - ((v - min) / range) * (H - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="spa-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linejoin="round"/>
  </svg>`;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function num(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString();
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function showError(msg) {
  elError.hidden      = false;
  elError.textContent = `Error: ${msg}`;
  elLoading.hidden    = true;
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
init();
