/* AI Dropshipping Agent — Dashboard JavaScript */
'use strict';

const API = (() => {
  const base = () => localStorage.getItem('api_base') || 'http://127.0.0.1:8000';
  const req = async (method, path, body) => {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(base() + path, opts);
    if (!r.ok) {
      let msg = `HTTP ${r.status}`;
      try { const e = await r.json(); msg = e.detail || JSON.stringify(e); } catch {}
      throw new Error(msg);
    }
    return r.json();
  };
  return {
    health:       ()   => req('GET',  '/health'),
    researchProduct:(b)=> req('POST', '/research/product', b),
    rankProducts: (b)  => req('POST', '/research/products/rank', b),
    pricing:      (b)  => req('POST', '/pricing', b),
    suppliers:    (b)  => req('POST', '/research/suppliers', b),
    opportunity:  (b)  => req('POST', '/evaluate/opportunity', b),
    content:      (b)  => req('POST', '/generate/content', b),
    marketing:    (b)  => req('POST', '/analyse/marketing', b),
    performance:  (b)  => req('POST', '/analyse/performance', b),
  };
})();

/* ── Routing ─────────────────────────────────────────────────── */
const PAGES = ['overview','discovery','research','suppliers',
               'pricing','opportunity','content','marketing','performance','settings'];

function navigate(page) {
  if (!PAGES.includes(page)) page = 'overview';
  document.querySelectorAll('nav li a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === page);
  });
  const title = document.querySelector(`[data-page="${page}"]`)?.textContent?.trim() || page;
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-breadcrumb').textContent = 'Dashboard › ' + title;
  renderPage(page);
  history.pushState({ page }, '', '#' + page);
  closeSidebar();
}

window.addEventListener('popstate', e => navigate(e.state?.page || 'overview'));

/* ── Utilities ───────────────────────────────────────────────── */
const qs = id => document.getElementById(id);
const html = s => s;

function setBtn(btn, loading) {
  if (loading) {
    btn._orig = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Working…';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn._orig || btn.innerHTML;
    btn.disabled = false;
  }
}

function showAlert(container, type, msg) {
  const icons = { success:'✓', error:'✗', warning:'⚠', info:'ℹ' };
  container.innerHTML = `<div class="alert alert-${type}">
    <span>${icons[type]||'•'}</span><span>${msg}</span></div>`;
}

function scoreColor(s) {
  if (s >= 70) return 'var(--success)';
  if (s >= 50) return 'var(--warning)';
  return 'var(--danger)';
}

function classificationBadge(c) {
  const map = {
    STRONG:'badge-success', MODERATE:'badge-info',
    WEAK:'badge-warning', POOR:'badge-danger',
    'INSUFFICIENT DATA':'badge-dim', RECOMMENDED:'badge-success',
    ACCEPTABLE:'badge-info', RISKY:'badge-warning',
    DISQUALIFIED:'badge-danger', 'HIGH OPPORTUNITY':'badge-success',
    'MODERATE OPPORTUNITY':'badge-info', 'LOW OPPORTUNITY':'badge-warning',
    'WEAK OPPORTUNITY':'badge-danger', 'INSUFFICIENT DATA':'badge-dim'
  };
  return `<span class="badge ${map[c]||'badge-dim'}">${c}</span>`;
}

function scoreBar(label, value, max=100) {
  const pct = Math.min(100, Math.round((value/max)*100));
  return `<div class="score-bar-wrap">
    <div class="score-bar-label"><span>${label}</span><span>${value?.toFixed?.(1)??value}</span></div>
    <div class="score-bar"><div class="score-bar-fill"
      style="width:${pct}%;background:${scoreColor(pct)}"></div></div></div>`;
}

function emptyState(icon, msg) {
  return `<div class="empty-state"><div class="empty-icon">${icon}</div><p>${msg}</p></div>`;
}

function copyBtn(text) {
  return `<button class="copy-btn" onclick="navigator.clipboard.writeText(${JSON.stringify(text)})
    .then(()=>{this.textContent='Copied!';setTimeout(()=>this.textContent='Copy',1500)})">Copy</button>`;
}

/* ── Tag input widget ─────────────────────────────────────────── */
function TagInput(wrapId) {
  const wrap = qs(wrapId);
  const input = wrap.querySelector('input');
  const tags = [];
  const render = () => {
    wrap.querySelectorAll('.tag-pill').forEach(p => p.remove());
    tags.forEach((t, i) => {
      const pill = document.createElement('span');
      pill.className = 'tag-pill';
      pill.innerHTML = `${t}<button onclick="this.closest('.tag-pill').remove();tags.splice(${i},1)">×</button>`;
      wrap.insertBefore(pill, input);
    });
  };
  input.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ',') && input.value.trim()) {
      e.preventDefault();
      tags.push(input.value.trim());
      input.value = '';
      render();
    }
    if (e.key === 'Backspace' && !input.value && tags.length) {
      tags.pop(); render();
    }
  });
  return { getTags: () => [...tags], clear: () => { tags.length = 0; render(); } };
}

/* ── Supplier row builder ─────────────────────────────────────── */
let supplierCount = 0;
function addSupplierRow(container) {
  supplierCount++;
  const id = supplierCount;
  const div = document.createElement('div');
  div.className = 'supplier-row'; div.id = `sup-row-${id}`;
  div.innerHTML = `
    <div class="supplier-row-title">Supplier ${id}</div>
    <button class="remove-row" onclick="document.getElementById('sup-row-${id}').remove()">×</button>
    <div class="form-row">
      <div class="form-group"><label>Supplier ID</label>
        <input type="text" id="sup-id-${id}" value="SUP-${id}" /></div>
      <div class="form-group"><label>Unit Cost (USD)</label>
        <input type="number" id="sup-cost-${id}" step="0.01" placeholder="8.50" /></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Availability</label>
        <select id="sup-avail-${id}">
          <option>UNKNOWN</option><option>IN_STOCK</option>
          <option>LOW_STOCK</option><option>OUT_OF_STOCK</option></select></div>
      <div class="form-group"><label>Platform Rating (0–5)</label>
        <input type="number" id="sup-rating-${id}" step="0.1" min="0" max="5" placeholder="4.5"/></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Review Count</label>
        <input type="number" id="sup-reviews-${id}" placeholder="500"/></div>
      <div class="form-group"><label>Years Active</label>
        <input type="number" id="sup-years-${id}" placeholder="5"/></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Max Delivery Days</label>
        <input type="number" id="sup-days-${id}" placeholder="14"/></div>
      <div class="form-group"><label>Shipping Cost (USD)</label>
        <input type="number" id="sup-ship-${id}" step="0.01" placeholder="2.00"/></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label>Tracked Shipping</label>
        <select id="sup-tracked-${id}">
          <option value="">Unknown</option>
          <option value="true">Yes</option><option value="false">No</option></select></div>
      <div class="form-group"><label>Return Policy</label>
        <select id="sup-returns-${id}">
          <option value="">Unknown</option>
          <option value="true">Available</option><option value="false">Not available</option></select></div>
    </div>`;
  container.appendChild(div);
}

function collectSuppliers() {
  const rows = document.querySelectorAll('.supplier-row');
  return Array.from(rows).map(row => {
    const id = row.id.split('-')[2];
    const v = k => { const el = qs(`sup-${k}-${id}`); return el ? el.value : ''; };
    const n = k => { const el = qs(`sup-${k}-${id}`); return el?.value ? parseFloat(el.value) : null; };
    const bool = k => { const val = v(k); return val === 'true' ? true : val === 'false' ? false : null; };
    return {
      supplier_id: v('id') || `SUP-${id}`,
      unit_cost_usd: n('cost'),
      currency: 'USD',
      availability: v('avail') || 'UNKNOWN',
      platform_rating: n('rating'),
      review_count: n('reviews') ? parseInt(n('reviews')) : null,
      years_active: n('years') ? parseInt(n('years')) : null,
      max_delivery_days: n('days') ? parseInt(n('days')) : null,
      shipping_cost_usd: n('ship'),
      has_tracked_shipping: bool('tracked'),
      return_policy_available: bool('returns'),
      minimum_order_quantity: 1,
    };
  });
}

/* ── Page renderers ───────────────────────────────────────────── */
function renderPage(page) {
  const content = qs('page-content');
  const renderers = {
    overview, discovery, research, suppliers,
    pricing, opportunity, content: contentPage,
    marketing, performance, settings
  };
  content.innerHTML = '';
  (renderers[page] || overview)();
}

/* ── OVERVIEW ────────────────────────────────────────────────── */
async function overview() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="icon">📡</span>Backend Status</div>
      <div id="health-result">${emptyState('⟳', 'Checking backend…')}</div>
    </div>
    <div class="card">
      <div class="card-title"><span class="icon">🔄</span>Pipeline</div>
      <div class="pipeline">
        <div class="pipe-step"><div class="step-num">Step 2</div>
          <div class="step-name">Pricing</div><div class="step-sub">Cost & margin</div></div>
        <div class="pipe-arrow">→</div>
        <div class="pipe-step"><div class="step-num">Step 3</div>
          <div class="step-name">Research</div><div class="step-sub">Demand & trends</div></div>
        <div class="pipe-arrow">→</div>
        <div class="pipe-step"><div class="step-num">Step 4</div>
          <div class="step-name">Suppliers</div><div class="step-sub">Compare & rank</div></div>
        <div class="pipe-arrow">→</div>
        <div class="pipe-step"><div class="step-num">Step 5</div>
          <div class="step-name">Opportunity</div><div class="step-sub">Evaluate potential</div></div>
        <div class="pipe-arrow">→</div>
        <div class="pipe-step"><div class="step-num">Step 6</div>
          <div class="step-name">Content</div><div class="step-sub">AI copywriting</div></div>
        <div class="pipe-arrow">→</div>
        <div class="pipe-step"><div class="step-num">Step 7</div>
          <div class="step-name">Marketing</div><div class="step-sub">Intelligence</div></div>
      </div>
    </div>
    <div class="grid-3">
      ${['discovery','research','suppliers','pricing','opportunity','content']
        .map(p => `<div class="stat-card" style="cursor:pointer" onclick="navigate('${p}')">
          <div class="stat-lbl" style="font-size:.85rem;font-weight:600;text-align:left">${p.charAt(0).toUpperCase()+p.slice(1)}</div></div>`).join('')}
    </div>`;
  try {
    const h = await API.health();
    qs('health-result').innerHTML = `
      <div class="grid-4">
        <div class="stat-card"><div class="stat-val text-success">●</div>
          <div class="stat-lbl">Status: ${h.status}</div></div>
        <div class="stat-card"><div class="stat-val">${h.version}</div>
          <div class="stat-lbl">Version</div></div>
        <div class="stat-card"><div class="stat-val">${h.tests_passing}</div>
          <div class="stat-lbl">Tests passing</div></div>
        <div class="stat-card"><div class="stat-val">${h.modules?.length??7}</div>
          <div class="stat-lbl">Modules</div></div>
      </div>
      <div class="mt-2"><div class="chip-group">
        ${(h.modules||[]).map(m=>`<span class="chip">${m}</span>`).join('')}
      </div></div>`;
  } catch(e) {
    qs('health-result').innerHTML = `<div class="alert alert-error">✗ Cannot reach backend: ${e.message}</div>`;
  }
}

/* ── DISCOVERY ───────────────────────────────────────────────── */
function discovery() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-title"><span class="icon">🔍</span>Evaluate a Product Idea</div>
        <div class="form-group"><label>Product ID</label>
          <input id="disc-pid" type="text" placeholder="PROD-001" value="PROD-001"/></div>
        <div class="form-group"><label>Demand Score (0–100)</label>
          <input id="disc-demand" type="number" min="0" max="100" placeholder="75"/></div>
        <div class="form-group"><label>Competition Score (0–100)</label>
          <input id="disc-comp" type="number" min="0" max="100" placeholder="60"/></div>
        <div class="form-group"><label>Trend Score (0–100)</label>
          <input id="disc-trend" type="number" min="0" max="100" placeholder="70"/></div>
        <div id="disc-alert"></div>
        <button class="btn btn-primary w-full" id="disc-btn" onclick="runDiscovery()">
          🔍 Evaluate</button>
      </div>
      <div id="disc-result"><div class="card">${emptyState('🔍','Enter scores and click Evaluate')}</div></div>
    </div>`;
}

async function runDiscovery() {
  const btn = qs('disc-btn');
  const alert = qs('disc-alert');
  const result = qs('disc-result');
  setBtn(btn, true); alert.innerHTML = '';
  const body = {
    product_id: qs('disc-pid').value || 'PROD-001',
    demand_score: parseFloat(qs('disc-demand').value) || null,
    competition_score: parseFloat(qs('disc-comp').value) || null,
    trend_score: parseFloat(qs('disc-trend').value) || null,
  };
  try {
    const r = await API.researchProduct(body);
    result.innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">📊</span>Research Result</div>
      <div style="text-align:center;padding:16px 0">
        <div class="score-big" style="color:${scoreColor(r.opportunity_score)}">${r.opportunity_score}</div>
        <div class="score-label">Opportunity Score</div>
        <div style="margin-top:10px">${classificationBadge(r.rating)}</div>
      </div>
      ${r.missing_fields?.length ? `<div class="alert alert-warning">⚠ Missing: ${r.missing_fields.join(', ')}</div>` : ''}
      <div class="result-section"><h3>Details</h3>
        <div class="result-list"><li>Product ID: ${r.product_id}</li>
        <li>Data verified: ${r.data_verified ? '✓ Yes' : '✗ No'}</li></div>
      </div></div>`;
  } catch(e) { showAlert(alert, 'error', e.message); }
  setBtn(btn, false);
}

/* ── PRODUCT RESEARCH (rank multiple) ────────────────────────── */
function research() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="icon">📈</span>Rank Multiple Products</div>
      <p class="text-sec" style="font-size:.85rem;margin-bottom:14px">
        Enter up to 10 products and rank them by opportunity score.</p>
      <div id="research-rows"></div>
      <button class="add-row-btn" onclick="addResearchRow()">+ Add Product</button>
      <div id="research-alert" class="mt-2"></div>
      <div class="mt-2">
        <button class="btn btn-primary" id="research-btn" onclick="runResearch()">
          📈 Rank Products</button>
      </div>
    </div>
    <div id="research-result"></div>`;
  addResearchRow(); addResearchRow(); addResearchRow();
}

let researchCount = 0;
function addResearchRow() {
  researchCount++;
  const id = researchCount;
  const wrap = qs('research-rows');
  const div = document.createElement('div');
  div.className = 'supplier-row'; div.id = `res-row-${id}`;
  div.innerHTML = `
    <div class="supplier-row-title">Product ${id}</div>
    <button class="remove-row" onclick="document.getElementById('res-row-${id}').remove()">×</button>
    <div class="form-row-3">
      <div class="form-group"><label>Product ID</label>
        <input type="text" id="res-pid-${id}" value="PROD-${id}"/></div>
      <div class="form-group"><label>Demand (0–100)</label>
        <input type="number" id="res-d-${id}" min="0" max="100"/></div>
      <div class="form-group"><label>Competition (0–100)</label>
        <input type="number" id="res-c-${id}" min="0" max="100"/></div>
    </div>
    <div class="form-row" style="grid-template-columns:1fr 2fr">
      <div class="form-group"><label>Trend (0–100)</label>
        <input type="number" id="res-t-${id}" min="0" max="100"/></div>
    </div>`;
  wrap.appendChild(div);
}

async function runResearch() {
  const btn = qs('research-btn');
  const alert = qs('research-alert');
  setBtn(btn, true); alert.innerHTML = '';
  const rows = document.querySelectorAll('#research-rows .supplier-row');
  const body = Array.from(rows).map(row => {
    const i = row.id.split('-')[2];
    const nv = k => { const el = qs(`res-${k}-${i}`); return el?.value ? parseFloat(el.value) : null; };
    return { product_id: qs(`res-pid-${i}`)?.value || `PROD-${i}`,
      demand_score: nv('d'), competition_score: nv('c'), trend_score: nv('t') };
  });
  try {
    const results = await API.rankProducts(body);
    qs('research-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">🏆</span>Ranked Results</div>
      <table class="data-table"><thead><tr>
        <th>#</th><th>Product ID</th><th>Score</th><th>Rating</th><th>Missing</th>
      </tr></thead><tbody>
      ${results.map((r,i) => `<tr>
        <td>${i+1}</td><td>${r.product_id}</td>
        <td style="color:${scoreColor(r.opportunity_score)};font-weight:700">${r.opportunity_score}</td>
        <td>${classificationBadge(r.rating)}</td>
        <td>${r.missing_fields?.length ? r.missing_fields.join(', ') : '—'}</td>
      </tr>`).join('')}
      </tbody></table></div>`;
  } catch(e) { showAlert(alert, 'error', e.message); }
  setBtn(btn, false);
}

/* ── SUPPLIERS ───────────────────────────────────────────────── */
function suppliers() {
  const c = qs('page-content');
  supplierCount = 0;
  c.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="icon">🏭</span>Compare Suppliers</div>
      <div class="form-group"><label>Product ID</label>
        <input id="sup-prod-id" type="text" value="PROD-001"/></div>
      <div id="supplier-rows"></div>
      <button class="add-row-btn" onclick="addSupplierRow(qs('supplier-rows'))">+ Add Supplier</button>
      <div id="sup-alert" class="mt-2"></div>
      <div class="mt-2">
        <button class="btn btn-primary" id="sup-btn" onclick="runSuppliers()">
          🏭 Compare</button>
      </div>
    </div>
    <div id="sup-result"></div>`;
  addSupplierRow(qs('supplier-rows'));
  addSupplierRow(qs('supplier-rows'));
}

async function runSuppliers() {
  const btn = qs('sup-btn');
  const alert = qs('sup-alert');
  setBtn(btn, true); alert.innerHTML = '';
  const body = { product_id: qs('sup-prod-id').value || 'PROD-001', suppliers: collectSuppliers() };
  if (!body.suppliers.length) { showAlert(alert,'warning','Add at least one supplier.'); setBtn(btn,false); return; }
  try {
    const r = await API.suppliers(body);
    const evals = r.ranked_evaluations || [];
    qs('sup-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">🏆</span>Comparison Results</div>
      ${r.recommended_supplier_id ? `<div class="alert alert-success">✓ Recommended: ${r.recommended_supplier_id}
        ${r.best_unit_cost_usd ? ` — Best cost: $${r.best_unit_cost_usd}` : ''}</div>` : ''}
      ${r.comparison_notes?.map(n=>`<div class="alert alert-info">ℹ ${n}</div>`).join('')||''}
      ${evals.map(e => `<div class="card" style="margin-bottom:12px">
        <div class="flex justify-between items-center mb-1">
          <strong>${e.supplier_id}</strong>${classificationBadge(e.recommendation)}</div>
        ${e.disqualified ? `<div class="alert alert-error">✗ ${e.disqualification_reason}</div>` : `
          ${scoreBar('Overall', e.overall_score)}
          ${scoreBar('Reliability', e.reliability_score)}
          ${scoreBar('Fulfilment', e.fulfilment_score)}
          ${scoreBar('Cost', e.cost_score)}`}
        ${e.cost_score_note ? `<div class="text-dim mt-1" style="font-size:.78rem">${e.cost_score_note}</div>` : ''}
        ${e.missing_fields?.length ? `<div class="text-warning mt-1" style="font-size:.78rem">Missing: ${e.missing_fields.join(', ')}</div>` : ''}
      </div>`).join('')}
    </div>`;
  } catch(e) { showAlert(alert, 'error', e.message); }
  setBtn(btn, false);
}

/* ── PRICING ─────────────────────────────────────────────────── */
function pricing() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-title"><span class="icon">💰</span>Pricing Calculator</div>
        <div class="form-group"><label>Supplier Cost (USD)</label>
          <input id="p-sup" type="number" step="0.01" placeholder="8.00" oninput="liveMargin()"/></div>
        <div class="form-group"><label>Shipping Cost (USD)</label>
          <input id="p-ship" type="number" step="0.01" placeholder="2.00" value="0" oninput="liveMargin()"/></div>
        <div class="form-group"><label>Other Costs (USD)</label>
          <input id="p-other" type="number" step="0.01" placeholder="0.00" value="0" oninput="liveMargin()"/></div>
        <div class="form-group"><label>Selling Price (USD)</label>
          <input id="p-sell" type="number" step="0.01" placeholder="22.00" oninput="liveMargin()"/></div>
        <div id="p-preview" class="card mt-2" style="background:var(--bg-input)">
          <div class="text-dim" style="font-size:.8rem">Live preview — enter values above</div>
        </div>
        <div id="p-alert" class="mt-2"></div>
        <button class="btn btn-primary w-full mt-2" id="p-btn" onclick="runPricing()">
          💰 Calculate</button>
      </div>
      <div id="p-result"><div class="card">${emptyState('💰','Enter costs and click Calculate')}</div></div>
    </div>`;
}

function liveMargin() {
  const sup = parseFloat(qs('p-sup').value)||0;
  const ship= parseFloat(qs('p-ship').value)||0;
  const oth = parseFloat(qs('p-other').value)||0;
  const sell= parseFloat(qs('p-sell').value)||0;
  const cost = sup+ship+oth;
  const profit = sell - cost;
  const margin = sell > 0 ? ((profit/sell)*100).toFixed(2) : '—';
  const col = profit > 0 ? 'var(--success)' : 'var(--danger)';
  qs('p-preview').innerHTML = `
    <div class="grid-2">
      <div><div class="stat-val" style="font-size:1.3rem">$${cost.toFixed(2)}</div>
        <div class="stat-lbl">Total Cost</div></div>
      <div><div class="stat-val" style="font-size:1.3rem;color:${col}">$${profit.toFixed(2)}</div>
        <div class="stat-lbl">Gross Profit</div></div>
    </div>
    <div style="text-align:center;margin-top:10px">
      <span style="font-size:1.5rem;font-weight:700;color:${col}">${margin}%</span>
      <div class="stat-lbl">Gross Margin</div></div>`;
}

async function runPricing() {
  const btn = qs('p-btn'); const alert = qs('p-alert');
  setBtn(btn,true); alert.innerHTML='';
  const body = {
    supplier_cost: parseFloat(qs('p-sup').value),
    shipping_cost: parseFloat(qs('p-ship').value)||0,
    other_costs:   parseFloat(qs('p-other').value)||0,
    selling_price: parseFloat(qs('p-sell').value),
  };
  try {
    const r = await API.pricing(body);
    const col = r.is_viable ? 'var(--success)' : 'var(--danger)';
    qs('p-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">📊</span>Pricing Result</div>
      <div class="grid-2">
        <div class="stat-card"><div class="stat-val">$${r.total_landed_cost}</div>
          <div class="stat-lbl">Total Landed Cost</div></div>
        <div class="stat-card"><div class="stat-val" style="color:${col}">$${r.gross_profit}</div>
          <div class="stat-lbl">Gross Profit</div></div>
        <div class="stat-card"><div class="stat-val" style="color:${col}">${r.gross_margin_pct}%</div>
          <div class="stat-lbl">Gross Margin</div></div>
        <div class="stat-card"><div class="stat-val">${r.is_viable?'✓ Viable':'✗ Not viable'}</div>
          <div class="stat-lbl" style="color:${col}">Viability</div></div>
      </div>
      <div class="alert ${r.is_viable?'alert-success':'alert-error'} mt-2">
        ${r.is_viable?'✓ This product is viable at the current pricing.':'✗ Costs exceed selling price — product is not viable.'}</div>
    </div>`;
  } catch(e) { showAlert(alert,'error',e.message); }
  setBtn(btn,false);
}

/* ── OPPORTUNITY ─────────────────────────────────────────────── */
function opportunity() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div>
        <div class="card">
          <div class="card-title"><span class="icon">🎯</span>Market Research</div>
          <div class="form-group"><label>Product ID</label>
            <input id="opp-pid" value="PROD-001"/></div>
          <div class="form-group"><label>Opportunity Score (0–100)</label>
            <input id="opp-score" type="number" min="0" max="100" placeholder="70.5"/></div>
          <div class="form-group"><label>Research Rating</label>
            <select id="opp-rating">
              <option>HIGH OPPORTUNITY</option><option selected>MODERATE OPPORTUNITY</option>
              <option>LOW OPPORTUNITY</option><option>WEAK OPPORTUNITY</option>
              <option>INSUFFICIENT DATA</option></select></div>
        </div>
        <div class="card">
          <div class="card-title"><span class="icon">🏭</span>Supplier</div>
          <div class="form-group"><label>Best Unit Cost (USD)</label>
            <input id="opp-cost" type="number" step="0.01" placeholder="8.00"/></div>
          <div class="form-group"><label>Supplier Score (0–100)</label>
            <input id="opp-sscore" type="number" placeholder="72"/></div>
        </div>
        <div class="card">
          <div class="card-title"><span class="icon">💲</span>Pricing</div>
          <div class="form-group"><label>Selling Price (USD)</label>
            <input id="opp-price" type="number" step="0.01" placeholder="22.00"/></div>
          <div class="form-group"><label>Other Costs (USD)</label>
            <input id="opp-other" type="number" step="0.01" placeholder="0" value="0"/></div>
        </div>
        <div id="opp-alert"></div>
        <button class="btn btn-primary w-full" id="opp-btn" onclick="runOpportunity()">
          🎯 Evaluate</button>
      </div>
      <div id="opp-result"><div class="card">${emptyState('🎯','Fill in the form and click Evaluate')}</div></div>
    </div>`;
}

async function runOpportunity() {
  const btn=qs('opp-btn'); const alert=qs('opp-alert');
  setBtn(btn,true); alert.innerHTML='';
  const body = {
    product_id: qs('opp-pid').value||'PROD-001',
    research_opportunity_score: parseFloat(qs('opp-score').value)||null,
    research_rating: qs('opp-rating').value,
    best_unit_cost_usd: parseFloat(qs('opp-cost').value)||null,
    best_supplier_overall_score: parseFloat(qs('opp-sscore').value)||null,
    selling_price_usd: parseFloat(qs('opp-price').value)||null,
    other_costs_usd: parseFloat(qs('opp-other').value)||0,
  };
  try {
    const r = await API.opportunity(body);
    const col = scoreColor(r.overall_score);
    qs('opp-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">🎯</span>Opportunity Result</div>
      <div style="text-align:center;padding:16px 0">
        <div class="score-big" style="color:${col}">${r.overall_score}</div>
        <div class="score-label">Overall Score</div>
        <div style="margin-top:10px">${classificationBadge(r.classification)}</div>
      </div>
      ${scoreBar('Market', r.market_score)}
      ${scoreBar('Supplier', r.supplier_score)}
      ${scoreBar('Pricing', r.pricing_score)}
      ${r.estimated_margin_pct!=null?`<div class="alert ${r.is_viable?'alert-success':'alert-warning'} mt-2">
        Gross margin: ${r.estimated_margin_pct}% — ${r.is_viable?'Viable':'Not viable'}</div>`:''}
      ${r.strengths?.length?`<div class="result-section"><h3>Strengths</h3><ul class="result-list">
        ${r.strengths.map(s=>`<li>${s}</li>`).join('')}</ul></div>`:''}
      ${r.weaknesses?.length?`<div class="result-section"><h3>Weaknesses</h3><ul class="result-list">
        ${r.weaknesses.map(s=>`<li>${s}</li>`).join('')}</ul></div>`:''}
      ${r.risks?.length?`<div class="result-section"><h3>Risks</h3><ul class="result-list">
        ${r.risks.map(s=>`<li>${s}</li>`).join('')}</ul></div>`:''}
      ${r.recommendation_basis?`<div class="alert alert-info mt-2">ℹ ${r.recommendation_basis}</div>`:''}
      ${r.missing_information?.length?`<div class="alert alert-warning mt-2">⚠ Missing: ${r.missing_information.join(', ')}</div>`:''}
    </div>`;
  } catch(e) { showAlert(alert,'error',e.message); }
  setBtn(btn,false);
}

/* ── CONTENT GENERATOR ───────────────────────────────────────── */
let featureTags;
function contentPage() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-title"><span class="icon">✍️</span>Generate Content</div>
        <div class="form-group"><label>Product ID</label>
          <input id="cg-pid" value="PROD-001"/></div>
        <div class="form-group"><label>Product Name *</label>
          <input id="cg-name" placeholder="Rechargeable LED Lantern"/></div>
        <div class="form-group"><label>Category</label>
          <input id="cg-cat" placeholder="Home & Outdoors"/></div>
        <div class="form-group"><label>Description</label>
          <textarea id="cg-desc" placeholder="A reliable LED lantern…"></textarea></div>
        <div class="form-group"><label>Known Features (press Enter to add)</label>
          <div class="tag-input-wrap" id="cg-feat-wrap"><input id="cg-feat-inp" placeholder="Add feature…"/></div></div>
        <div class="form-group"><label>Selling Price (USD)</label>
          <input id="cg-price" type="number" step="0.01" placeholder="22.00"/></div>
        <div class="form-row">
          <div class="form-group"><label>Channel</label>
            <select id="cg-channel">
              <option value="PRODUCT_LISTING">Product Listing</option>
              <option value="SOCIAL_MEDIA">Social Media</option>
              <option value="PAID_ADS">Paid Ads</option>
              <option value="EMAIL">Email</option>
              <option value="SEO">SEO</option></select></div>
          <div class="form-group"><label>Tone</label>
            <select id="cg-tone">
              <option value="PROFESSIONAL">Professional</option>
              <option value="CASUAL">Casual</option>
              <option value="ENTHUSIASTIC">Enthusiastic</option>
              <option value="MINIMALIST">Minimalist</option></select></div>
        </div>
        <div class="form-group"><label>Variations</label>
          <input id="cg-vars" type="number" min="1" max="5" value="1"/></div>
        <div class="form-group"><label>Content Types</label>
          <div class="chip-group">
            ${['PRODUCT_TITLE','SHORT_SUMMARY','BULLET_POINTS','SEO_KEYWORDS',
               'META_DESCRIPTION','PRODUCT_DESC','SOCIAL_CAPTION','AD_COPY','MARKETING_ANGLE']
              .map(t=>`<label style="display:flex;align-items:center;gap:5px;cursor:pointer">
                <input type="checkbox" class="cg-type" value="${t}" ${['PRODUCT_TITLE','SHORT_SUMMARY','BULLET_POINTS','SEO_KEYWORDS','META_DESCRIPTION'].includes(t)?'checked':''}/>
                <span class="chip">${t}</span></label>`).join('')}
          </div></div>
        <div id="cg-alert" class="mt-2"></div>
        <button class="btn btn-primary w-full mt-2" id="cg-btn" onclick="runContent()">
          ✍️ Generate</button>
      </div>
      <div id="cg-result"><div class="card">${emptyState('✍️','Fill in product details and click Generate')}</div></div>
    </div>`;
  featureTags = TagInput('cg-feat-wrap');
}

async function runContent() {
  const btn=qs('cg-btn'); const alert=qs('cg-alert');
  setBtn(btn,true); alert.innerHTML='';
  const types = Array.from(document.querySelectorAll('.cg-type:checked')).map(el=>el.value);
  if (!types.length) { showAlert(alert,'warning','Select at least one content type.'); setBtn(btn,false); return; }
  const body = {
    product_id: qs('cg-pid').value||'PROD-001',
    product_name: qs('cg-name').value,
    product_category: qs('cg-cat').value,
    product_description: qs('cg-desc').value,
    known_features: featureTags.getTags(),
    selling_price_usd: parseFloat(qs('cg-price').value)||null,
    content_types: types,
    channel: qs('cg-channel').value,
    tone: qs('cg-tone').value,
    variations: parseInt(qs('cg-vars').value)||1,
  };
  try {
    const r = await API.content(body);
    if (r.generation_failed) { showAlert(alert,'error',r.failure_reason); setBtn(btn,false); return; }
    const byType = {};
    (r.items||[]).forEach(item => {
      if (!byType[item.content_type]) byType[item.content_type] = [];
      byType[item.content_type].push(item);
    });
    const tabs = Object.keys(byType);
    qs('cg-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">📄</span>Generated Content</div>
      ${r.missing_product_information?.length?`<div class="alert alert-warning mb-1">⚠ Missing info: ${r.missing_product_information.join(', ')}</div>`:''}
      ${r.accuracy_warnings?.length?`<div class="alert alert-warning mb-1">⚠ Accuracy: ${r.accuracy_warnings.join(' | ')}</div>`:''}
      <div class="tabs">${tabs.map((t,i)=>`<button class="tab-btn ${i===0?'active':''}"
        onclick="switchTab(this,'cgtab-${i}')">${t}</button>`).join('')}</div>
      ${tabs.map((t,i)=>`<div class="tab-panel ${i===0?'active':''}" id="cgtab-${i}">
        ${byType[t].map(item=>`<div class="content-item">
          <div class="content-item-header">
            <span class="badge badge-dim">Variation ${item.variation_index+1}</span>
            <span style="display:flex;gap:6px;align-items:center">
              <span class="badge ${item.verification_flag==='VERIFIED'?'badge-success':'badge-dim'}">${item.verification_flag}</span>
              ${copyBtn(item.text)}</span></div>
          ${item.text_list?.length
            ? `<ul class="content-item-list">${item.text_list.map(li=>`<li>${li}</li>`).join('')}</ul>`
            : `<div class="content-item-text">${item.text}</div>`}
          ${item.grounding_notes?`<div class="text-dim mt-1" style="font-size:.75rem">${item.grounding_notes}</div>`:''}
        </div>`).join('')}
      </div>`).join('')}
    </div>`;
  } catch(e) { showAlert(alert,'error',e.message); }
  setBtn(btn,false);
}

function switchTab(btn, panelId) {
  const parent = btn.closest('.card');
  parent.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  parent.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  parent.querySelector('#'+panelId)?.classList.add('active');
}

/* ── MARKETING INTELLIGENCE ──────────────────────────────────── */
function marketing() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-title"><span class="icon">📡</span>Marketing Intelligence</div>
        <div class="form-group"><label>Product ID</label><input id="mk-pid" value="PROD-001"/></div>
        <div class="form-group"><label>Product Name *</label>
          <input id="mk-name" placeholder="Rechargeable LED Lantern"/></div>
        <div class="form-group"><label>Category</label><input id="mk-cat" placeholder="Home & Outdoors"/></div>
        <div class="form-group"><label>Selling Price (USD)</label>
          <input id="mk-price" type="number" step="0.01" placeholder="22.00"/></div>
        <div class="form-group"><label>Target Market</label>
          <input id="mk-market" placeholder="Global, UK, US…"/></div>
        <div class="form-group"><label>Audience Notes</label>
          <input id="mk-audience" placeholder="Your existing audience assumptions…"/></div>
        <div class="form-group"><label>Market Score (0–100)</label>
          <input id="mk-score" type="number" min="0" max="100" placeholder="70"/></div>
        <div class="form-group"><label>Opportunity Classification</label>
          <select id="mk-class">
            <option value="">— not set —</option>
            <option>STRONG</option><option>MODERATE</option>
            <option>WEAK</option><option>POOR</option></select></div>
        <div id="mk-alert" class="mt-2"></div>
        <button class="btn btn-primary w-full mt-2" id="mk-btn" onclick="runMarketing()">
          📡 Analyse</button>
      </div>
      <div id="mk-result"><div class="card">${emptyState('📡','Fill in product details and click Analyse')}</div></div>
    </div>`;
}

async function runMarketing() {
  const btn=qs('mk-btn'); const alert=qs('mk-alert');
  setBtn(btn,true); alert.innerHTML='';
  const body = {
    product_id: qs('mk-pid').value||'PROD-001',
    product_name: qs('mk-name').value,
    product_category: qs('mk-cat').value,
    selling_price_usd: parseFloat(qs('mk-price').value)||null,
    target_market: qs('mk-market').value,
    operator_audience_notes: qs('mk-audience').value,
    market_score: parseFloat(qs('mk-score').value)||null,
    opportunity_classification: qs('mk-class').value||null,
  };
  try {
    const r = await API.marketing(body);
    if (r.generation_failed) { showAlert(alert,'error',r.failure_reason); setBtn(btn,false); return; }
    qs('mk-result').innerHTML = `<div class="card">
      <div class="card-title"><span class="icon">📡</span>Intelligence Report</div>
      ${r.recommended_primary_channel?`<div class="alert alert-info">
        📌 Recommended channel: <strong>${r.recommended_primary_channel}</strong></div>`:''}
      ${r.audience_profile?`<div class="result-section"><h3>Audience Profile</h3>
        <div class="card" style="background:var(--bg-input)">
          <strong>${r.audience_profile.primary_segment}</strong>
          <span class="badge badge-dim ml-1">${r.audience_profile.confidence}</span>
          ${r.audience_profile.secondary_segments?.length?`<div class="chip-group mt-1">
            ${r.audience_profile.secondary_segments.map(s=>`<span class="chip">${s}</span>`).join('')}</div>`:''}
          <div class="mt-1 text-sec" style="font-size:.82rem">
            <strong>Motivations:</strong> ${r.audience_profile.buying_motivations?.join(', ')||'—'}</div>
          <div class="mt-1 text-sec" style="font-size:.82rem">
            <strong>Pain points:</strong> ${r.audience_profile.pain_points?.join(', ')||'—'}</div>
          <div class="mt-1 text-dim" style="font-size:.75rem">${r.audience_profile.basis}</div>
        </div></div>`:''}
      ${r.channel_recommendations?.length?`<div class="result-section"><h3>Channel Recommendations</h3>
        ${r.channel_recommendations.map(ch=>`<div class="flex justify-between items-center" style="padding:7px 0;border-bottom:1px solid var(--border)">
          <span>${ch.channel}</span>
          <span class="badge ${ch.suitability==='HIGH'?'badge-success':ch.suitability==='MEDIUM'?'badge-info':'badge-warning'}">${ch.suitability}</span>
          </div><div class="text-sec" style="font-size:.8rem;padding:4px 0 8px">${ch.rationale}</div>`).join('')}
        </div>`:''}
      ${r.positioning?`<div class="result-section"><h3>Positioning</h3>
        <div class="card" style="background:var(--bg-input)">
          <div style="font-weight:600;margin-bottom:8px">${r.positioning.value_proposition}</div>
          ${r.positioning.messaging_themes?.length?`<div class="chip-group">
            ${r.positioning.messaging_themes.map(t=>`<span class="chip">${t}</span>`).join('')}</div>`:''}
          <div class="mt-1 text-sec" style="font-size:.8rem">
            Tone: <strong>${r.positioning.tone_recommendation}</strong></div>
        </div></div>`:''}
      ${r.assumptions?.length?`<div class="alert alert-info mt-2">ℹ Assumptions: ${r.assumptions.join(' | ')}</div>`:''}
      ${r.warnings?.length?`<div class="alert alert-warning mt-1">⚠ ${r.warnings.join(' | ')}</div>`:''}
    </div>`;
  } catch(e) { showAlert(alert,'error',e.message); }
  setBtn(btn,false);
}

/* ── CAMPAIGN PERFORMANCE ────────────────────────────────────── */
function performance() {
  const c = qs('page-content');
  c.innerHTML = `
    <div class="two-col">
      <div class="card">
        <div class="card-title"><span class="icon">📊</span>Campaign Metrics</div>
        <div class="form-row">
          <div class="form-group"><label>Product ID</label>
            <input id="pf-pid" value="PROD-001"/></div>
          <div class="form-group"><label>Period</label>
            <input id="pf-period" value="Week 1"/></div>
        </div>
        <div class="form-group"><label>Channel</label>
          <select id="pf-channel">
            <option value="PAID_ADS">Paid Ads</option>
            <option value="SOCIAL_MEDIA">Social Media</option>
            <option value="SEO">SEO</option>
            <option value="EMAIL">Email</option>
            <option value="PRODUCT_LISTING">Product Listing</option></select></div>
        <div class="form-row">
          <div class="form-group"><label>Impressions</label>
            <input id="pf-imp" type="number" placeholder="10000"/></div>
          <div class="form-group"><label>Clicks</label>
            <input id="pf-clicks" type="number" placeholder="250"/></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Conversions</label>
            <input id="pf-conv" type="number" placeholder="10"/></div>
          <div class="form-group"><label>Spend (USD)</label>
            <input id="pf-spend" type="number" step="0.01" placeholder="100.00"/></div>
        </div>
        <div class="form-group"><label>Revenue (USD)</label>
          <input id="pf-rev" type="number" step="0.01" placeholder="400.00"/></div>
        <div id="pf-alert" class="mt-2"></div>
        <button class="btn btn-primary w-full mt-2" id="pf-btn" onclick="runPerformance()">
          📊 Analyse</button>
      </div>
      <div id="pf-result"><div class="card">${emptyState('📊','Enter campaign data and click Analyse')}</div></div>
    </div>`;
}

async function runPerformance() {
  const btn=qs('pf-btn'); const alert=qs('pf-alert');
  setBtn(btn,true); alert.innerHTML='';
  const int = id => { const v=qs(id)?.value; return v?parseInt(v):null; };
  const flt = id => { const v=qs(id)?.value; return v?parseFloat(v):null; };
  const body = {
    product_id: qs('pf-pid').value||'PROD-001',
    channel: qs('pf-channel').value,
    period_label: qs('pf-period').value||'Period 1',
    impressions: int('pf-imp'), clicks: int('pf-clicks'),
    conversions: int('pf-conv'), spend_usd: flt('pf-spend'), revenue_usd: flt('pf-rev'),
  };
  try {
    const r = await API.performance(body);
    const cm = r.computed_metrics;
    const ratingClass = r.performance_rating==='STRONG'?'badge-success':
      r.performance_rating==='ACCEPTABLE'?'badge-info':
      r.performance_rating==='POOR'?'badge-danger':'badge-dim';
    const fmt = v => v!=null ? v.toFixed(2) : '—';
    const fmtPct = v => v!=null ? v.toFixed(2)+'%' : '—';
    const fmtX = v => v!=null ? v.toFixed(2)+'×' : '—';
    qs('pf-result').innerHTML = `<div class="card">
      <div class="card-title flex justify-between">
        <span><span class="icon">📊</span> Performance Report</span>
        <span class="badge ${ratingClass}">${r.performance_rating}</span>
      </div>
      <div class="grid-3">
        <div class="metric-card"><div class="metric-val">${fmtPct(cm.ctr_pct)}</div>
          <div class="metric-lbl">CTR</div></div>
        <div class="metric-card"><div class="metric-val">${fmtPct(cm.conversion_rate_pct)}</div>
          <div class="metric-lbl">Conversion Rate</div></div>
        <div class="metric-card"><div class="metric-val">${fmtX(cm.roas)}</div>
          <div class="metric-lbl">ROAS</div></div>
        <div class="metric-card"><div class="metric-val">$${fmt(cm.cost_per_click_usd)}</div>
          <div class="metric-lbl">Cost per Click</div></div>
        <div class="metric-card"><div class="metric-val">$${fmt(cm.cost_per_conversion_usd)}</div>
          <div class="metric-lbl">Cost per Conv.</div></div>
        <div class="metric-card"><div class="metric-val">${cm.impressions??'—'}</div>
          <div class="metric-lbl">Impressions</div></div>
      </div>
      ${r.missing_metrics?.length?`<div class="alert alert-warning mt-2">⚠ Not calculated: ${r.missing_metrics.join(' | ')}</div>`:''}
      ${r.observations?.length?`<div class="result-section"><h3>Observations</h3><ul class="result-list">
        ${r.observations.map(o=>`<li>${o}</li>`).join('')}</ul></div>`:''}
      ${r.recommendations?.length?`<div class="result-section"><h3>Recommendations</h3><ul class="result-list">
        ${r.recommendations.map(o=>`<li>${o}</li>`).join('')}</ul></div>`:''}
    </div>`;
  } catch(e) { showAlert(alert,'error',e.message); }
  setBtn(btn,false);
}

/* ── SETTINGS ────────────────────────────────────────────────── */
function settings() {
  const c = qs('page-content');
  const saved = localStorage.getItem('api_base') || 'http://127.0.0.1:8000';
  c.innerHTML = `
    <div class="card" style="max-width:520px">
      <div class="card-title"><span class="icon">⚙️</span>Settings</div>
      <div class="form-group"><label>Backend API URL</label>
        <input id="set-url" value="${saved}" placeholder="http://127.0.0.1:8000"/>
        <small class="text-dim">The URL of your running FastAPI server.</small></div>
      <div class="form-row mt-2">
        <button class="btn btn-primary" onclick="saveSettings()">Save</button>
        <button class="btn btn-secondary" onclick="testBackend()">Test Connection</button>
      </div>
      <div id="set-alert" class="mt-2"></div>
      <div class="divider"></div>
      <div class="form-group"><label>Theme</label>
        <div style="display:flex;gap:10px;margin-top:6px">
          <button class="btn btn-secondary" onclick="setTheme('dark')">🌙 Dark</button>
          <button class="btn btn-secondary" onclick="setTheme('light')">☀️ Light</button>
        </div></div>
      <div class="divider"></div>
      <div class="alert alert-info">
        ℹ API credentials are kept in backend environment variables (.env file).
        Never enter API keys in this form.</div>
    </div>`;
}

function saveSettings() {
  const url = qs('set-url').value.trim();
  if (url) { localStorage.setItem('api_base', url); showAlert(qs('set-alert'),'success','Saved.'); }
}
async function testBackend() {
  try { const h = await API.health(); showAlert(qs('set-alert'),'success',`Connected — v${h.version}`); }
  catch(e) { showAlert(qs('set-alert'),'error',`Cannot reach backend: ${e.message}`); }
}

/* ── Theme & sidebar ─────────────────────────────────────────── */
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  qs('theme-label').textContent = t==='dark'?'☀️ Light':'🌙 Dark';
}
function toggleTheme() {
  setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');
}
function openSidebar() {
  qs('sidebar').classList.add('open');
  qs('sidebar-overlay').classList.add('show');
}
function closeSidebar() {
  qs('sidebar').classList.remove('open');
  qs('sidebar-overlay').classList.remove('show');
}

/* ── Backend status indicator ────────────────────────────────── */
async function checkStatus() {
  const dot = qs('status-dot');
  const lbl = qs('status-label');
  try {
    await API.health();
    dot.className='status-dot online'; lbl.textContent='Backend: Running';
  } catch {
    dot.className='status-dot offline'; lbl.textContent='Backend: Offline';
  }
}

/* ── Boot ────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const savedTheme = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  qs('theme-label').textContent = savedTheme==='dark'?'☀️ Light':'🌙 Dark';

  document.querySelectorAll('nav li a').forEach(a => {
    a.addEventListener('click', e => { e.preventDefault(); navigate(a.dataset.page); });
  });

  const hash = location.hash.replace('#','') || 'overview';
  navigate(hash);
  checkStatus();
  setInterval(checkStatus, 15000);
});
