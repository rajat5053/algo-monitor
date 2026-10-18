/**
 * Algo Monitor v2.0 — Trading Dashboard Application
 * Handles dual-market separation (Indian + Crypto), real-time updates (5s),
 * market toggles, option chains, F&O securities, futures movers, and paper trading.
 */

const REFRESH_INTERVAL = 5000; // 5 seconds real-time poll
let activeTab = 'overview';
let activeFnoFilter = '';
let currentOcSymbol = 'NIFTY50';
let currentOcExpiry = '';
let currentOcConstituent = ''; // sub-filter: constituent stock of a selected index
let marketToggles = { indian_enabled: true, crypto_enabled: true };
let previousPrices = {};
let indexConstituentsCache = null; // cached response from /api/indian/index-constituents

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    setupMarketToggles();
    setupFnoFilters();
    setupOptionChainSelector();
    setupUpstoxAuth();
    
    // Initial fetch
    refreshAll();
    
    // Continuous polling
    setInterval(refreshAll, REFRESH_INTERVAL);
});

// --- Tab Navigation ---
function setupTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            const content = document.getElementById(`tab-${target}`);
            if (content) content.classList.add('active');
            activeTab = target;

            // Trigger immediate refresh for specific tabs
            if (target === 'optionchain') {
                refreshOptionChain();
            } else if (target === 'indian') {
                refreshIndianMarket();
            } else if (target === 'crypto') {
                refreshCryptoMarket();
            }
        });
    });
}

// --- Market Toggles ---
function setupMarketToggles() {
    const indianSwitch = document.querySelector('#toggle-indian input');
    const cryptoSwitch = document.querySelector('#toggle-crypto input');

    // Fetch initial toggle state
    fetchJSON('/api/market-toggle').then(state => {
        if (state) {
            marketToggles = state;
            if (indianSwitch) indianSwitch.checked = state.indian_enabled;
            if (cryptoSwitch) cryptoSwitch.checked = state.crypto_enabled;
            applyMarketToggleUI();
        }
    });

    if (indianSwitch) {
        indianSwitch.addEventListener('change', async (e) => {
            marketToggles.indian_enabled = e.target.checked;
            applyMarketToggleUI();
            await fetch('/api/market-toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ indian_enabled: e.target.checked })
            });
            refreshAll();
        });
    }

    if (cryptoSwitch) {
        cryptoSwitch.addEventListener('change', async (e) => {
            marketToggles.crypto_enabled = e.target.checked;
            applyMarketToggleUI();
            await fetch('/api/market-toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ crypto_enabled: e.target.checked })
            });
            refreshAll();
        });
    }
}

function applyMarketToggleUI() {
    // Overview sections
    const ovIndian = document.getElementById('overview-indian-section');
    const ovCrypto = document.getElementById('overview-crypto-section');
    if (ovIndian) ovIndian.style.display = marketToggles.indian_enabled ? 'block' : 'none';
    if (ovCrypto) ovCrypto.style.display = marketToggles.crypto_enabled ? 'block' : 'none';

    // Indian Tab content
    const inNotice = document.getElementById('indian-disabled-notice');
    const inContent = document.getElementById('indian-market-content');
    if (inNotice && inContent) {
        inNotice.style.display = marketToggles.indian_enabled ? 'none' : 'block';
        inContent.style.display = marketToggles.indian_enabled ? 'block' : 'none';
    }

    // Crypto Tab content
    const crNotice = document.getElementById('crypto-disabled-notice');
    const crContent = document.getElementById('crypto-market-content');
    if (crNotice && crContent) {
        crNotice.style.display = marketToggles.crypto_enabled ? 'none' : 'block';
        crContent.style.display = marketToggles.crypto_enabled ? 'block' : 'none';
    }
}

// --- F&O Filter Buttons ---
function setupFnoFilters() {
    document.querySelectorAll('.fno-filters .filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.fno-filters .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeFnoFilter = btn.dataset.filter || '';
            refreshIndianMarket();
        });
    });
}

// --- Option Chain Selector ---
window.handleConstituentChange = function(val) {
    currentOcConstituent = val || '';
    currentOcExpiry = '';
    // If a constituent is selected, load its option chain; else reload the index chain
    if (currentOcConstituent) {
        currentOcSymbol = currentOcConstituent;
    } else {
        // Reset back to the index
        const mainSel = document.getElementById('oc-symbol-select');
        if (mainSel) currentOcSymbol = mainSel.value;
    }
    refreshOptionChain();
};

function setupOptionChainSelector() {
    const sel = document.getElementById('oc-symbol-select');
    if (sel) {
        sel.addEventListener('change', (e) => {
            currentOcSymbol = e.target.value;
            currentOcExpiry = '';
            currentOcConstituent = '';
            updateConstituentDropdown(currentOcSymbol);
            refreshOptionChain();
        });
    }
    const expSel = document.getElementById('oc-expiry-select');
    if (expSel) {
        expSel.addEventListener('change', (e) => {
            currentOcExpiry = e.target.value;
            refreshOptionChain();
        });
    }
    const constSel = document.getElementById('oc-constituent-select');
    if (constSel) {
        const onConstChange = (e) => {
            window.handleConstituentChange(e.target.value);
        };
        constSel.addEventListener('change', onConstChange);
        constSel.addEventListener('input', onConstChange);
    }
    // Populate constituent dropdown on load based on default symbol
    updateConstituentDropdown(currentOcSymbol);
}

/**
 * Fetch index constituents (cached) and update constituent dropdown.
 * Only visible when an index with known constituents is selected.
 */
async function updateConstituentDropdown(symbol) {
    const constWrap = document.getElementById('oc-constituent-wrap');
    const constSel  = document.getElementById('oc-constituent-select');
    if (!constWrap || !constSel) return;

    if (!indexConstituentsCache) {
        const data = await fetchJSON('/api/indian/index-constituents');
        indexConstituentsCache = (data && data.indices) ? data.indices : {};
    }

    const indexData = indexConstituentsCache[symbol];
    if (indexData && indexData.constituents && indexData.constituents.length > 0) {
        constWrap.style.display = 'flex';
        constSel.innerHTML =
            `<option value="">All ${indexData.display} Stocks</option>` +
            indexData.constituents.map(c =>
                `<option value="${c.symbol}">${c.display_name}</option>`
            ).join('');
        constSel.value = '';
        currentOcConstituent = '';
    } else {
        constWrap.style.display = 'none';
        constSel.innerHTML = '';
        currentOcConstituent = '';
    }
}

function switchToOptionChain(symbol) {
    const navBtn = document.querySelector('.nav-tab[data-tab="optionchain"]');
    const sel    = document.getElementById('oc-symbol-select');
    if (navBtn) navBtn.click();

    currentOcExpiry = '';
    currentOcConstituent = '';

    const indexSymbols = ['NIFTY50', 'BANKNIFTY', 'NIFTYAUTO', 'NIFTYMIDCAPSELECT'];
    if (indexSymbols.includes(symbol)) {
        if (sel) sel.value = symbol;
        currentOcSymbol = symbol;
        updateConstituentDropdown(symbol);
    } else {
        // Stock — ensure it's in the dropdown
        if (sel) {
            if (!Array.from(sel.options).some(o => o.value === symbol)) {
                const opt = document.createElement('option');
                opt.value = symbol;
                opt.textContent = symbol;
                sel.appendChild(opt);
            }
            sel.value = symbol;
        }
        currentOcSymbol = symbol;
        updateConstituentDropdown(symbol); // will hide constituent dropdown
    }
    refreshOptionChain();
}

// --- Data Fetching ---
async function fetchJSON(url) {
    try {
        const bustUrl = url + (url.includes('?') ? '&' : '?') + '_=' + Date.now();
        const resp = await fetch(bustUrl, { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (err) {
        console.warn(`Fetch error (${url}):`, err.message);
        return null;
    }
}

// --- Main Refresh Dispatcher ---
async function refreshAll() {
    // 1. Always update system status & metrics
    const [status, balance, positions] = await Promise.all([
        fetchJSON('/api/status'),
        fetchJSON('/api/balance'),
        fetchJSON('/api/positions'),
        refreshUpstoxStatus(),
    ]);

    if (status) renderStatus(status);
    if (balance) renderBalance(balance);
    if (positions) renderPositions(positions);

    // 2. Fetch market data according to toggles
    if (marketToggles.indian_enabled) {
        refreshIndianMarket();
    }

    if (marketToggles.crypto_enabled) {
        refreshCryptoMarket();
    }

    // 3. Tab-specific extra fetches
    if (activeTab === 'overview') {
        const [scanResults, zones] = await Promise.all([
            fetchJSON('/api/scan-results'),
            fetchJSON('/api/zones'),
        ]);
        if (scanResults) renderScanResults(scanResults);
        if (zones) renderZones(zones);
    } else if (activeTab === 'optionchain') {
        refreshOptionChain();
    } else if (activeTab === 'performance') {
        fetchJSON('/api/performance').then(p => { if (p) renderPerformance(p); });
    } else if (activeTab === 'settings') {
        fetchJSON('/api/config').then(c => { if (c) renderConfig(c); });
    }
}

// --- Status & Header ---
function renderStatus(data) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    const lastUpdate = document.getElementById('last-update');

    if (dot && label) {
        const isConnected = data.status === 'running';
        dot.className = `status-dot ${isConnected ? 'connected' : 'disconnected'}`;
        label.textContent = isConnected ? 'SYSTEM ACTIVE' : 'DISCONNECTED';
    }

    if (lastUpdate) {
        const d = new Date();
        lastUpdate.textContent = `Updated: ${d.toLocaleTimeString()}`;
    }
}

// --- Metrics & Balances ---
function renderBalance(data) {
    const balEl = document.getElementById('metric-balance');
    const pnlEl = document.getElementById('metric-daily-pnl');
    const tradesEl = document.getElementById('metric-daily-trades');

    if (balEl && data.total_equity !== undefined) {
        balEl.textContent = formatINR(data.total_equity);
    }
    if (pnlEl && data.daily_pnl !== undefined) {
        pnlEl.textContent = `${data.daily_pnl >= 0 ? '+' : ''}${formatINR(data.daily_pnl)}`;
        pnlEl.className = `metric-value ${data.daily_pnl >= 0 ? 'profit' : 'loss'}`;
    }
    if (tradesEl && data.daily_trades_count !== undefined) {
        tradesEl.textContent = data.daily_trades_count;
    }
}

// --- Indian Market Data ---
async function refreshIndianMarket() {
    const [indicesData, fnoData] = await Promise.all([
        fetchJSON('/api/indian/indices'),
        fetchJSON(`/api/indian/fno-securities?index_filter=${encodeURIComponent(activeFnoFilter)}`),
    ]);

    if (indicesData && indicesData.indices) {
        renderIndianIndices(indicesData.indices);
    }

    if (fnoData && fnoData.securities) {
        renderFnoSecurities(fnoData.securities);
    }
}

function renderIndianIndices(indices) {
    // 1. Update Overview Index Strip
    indices.forEach(idx => {
        const card = document.getElementById(`ticker-${idx.symbol}`);
        if (card) {
            const priceEl = card.querySelector('.ticker-price');
            const changeEl = card.querySelector('.ticker-change');
            if (priceEl && idx.ltp) {
                flashPriceUpdate(priceEl, idx.ltp, previousPrices[idx.symbol]);
                priceEl.textContent = formatINR(idx.ltp);
                previousPrices[idx.symbol] = idx.ltp;
            }
            if (changeEl && idx.change !== undefined) {
                const isPos = idx.change >= 0;
                changeEl.className = `ticker-change ${isPos ? 'positive' : 'negative'}`;
                changeEl.textContent = `${isPos ? '▲ +' : '▼ '}${idx.change.toFixed(2)} (${idx.change_pct ? idx.change_pct.toFixed(2) : '0.00'}%)`;
            }
        }
    });

    // 2. Update Indian Tab Detailed Indices Cards
    const container = document.getElementById('indices-cards');
    if (!container) return;

    container.innerHTML = indices.map(idx => {
        const isPos = (idx.change || 0) >= 0;
        return `
            <div class="card index-detail-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.75rem;">
                    <div>
                        <div style="font-weight:700;font-size:1.1rem;color:var(--text-primary)">${idx.display_name}</div>
                        <div class="font-mono text-muted" style="font-size:0.75rem">${idx.symbol}</div>
                    </div>
                    <button class="btn btn-sm btn-outline" onclick="switchToOptionChain('${idx.symbol}')" style="font-size:0.75rem;padding:0.25rem 0.6rem">
                        Chain 📊
                    </button>
                </div>
                <div style="display:flex;align-items:baseline;gap:0.75rem;margin-bottom:0.75rem;">
                    <span class="font-mono" style="font-size:1.5rem;font-weight:700;color:var(--text-primary)">
                        ${formatINR(idx.ltp || 0)}
                    </span>
                    <span class="ticker-change ${isPos ? 'positive' : 'negative'}" style="font-size:0.85rem">
                        ${isPos ? '▲ +' : '▼ '}${idx.change ? idx.change.toFixed(2) : '0.00'} (${idx.change_pct ? idx.change_pct.toFixed(2) : '0.00'}%)
                    </span>
                </div>
                <div class="grid-2 font-mono" style="font-size:0.75rem;color:var(--text-muted);border-top:1px solid var(--border-subtle);padding-top:0.5rem">
                    <div>Open: <span class="text-primary">${idx.open ? formatINR(idx.open) : '—'}</span></div>
                    <div>High: <span class="text-green">${idx.high ? formatINR(idx.high) : '—'}</span></div>
                    <div>Low: <span class="text-red">${idx.low ? formatINR(idx.low) : '—'}</span></div>
                    <div>Prev: <span class="text-secondary">${idx.prev_close ? formatINR(idx.prev_close) : '—'}</span></div>
                </div>
            </div>
        `;
    }).join('');
}

function renderFnoSecurities(securities) {
    const tableCard = document.getElementById('fno-table');
    if (!tableCard) return;

    if (!securities || securities.length === 0) {
        tableCard.innerHTML = `
            <div class="empty-state">
                <div class="icon">📈</div>
                <div class="title">No F&O Securities Found</div>
                <div class="desc">No instruments matched the selected index filter.</div>
            </div>
        `;
        return;
    }

    const rows = securities.map(sec => {
        const isPos = (sec.change || 0) >= 0;
        const changeClass = isPos ? 'text-green' : 'text-red';
        return `
            <tr>
                <td style="font-weight:600">
                    <span style="color:var(--text-primary)">${sec.display_name}</span>
                    <span class="font-mono text-muted" style="font-size:0.75rem;margin-left:0.5rem">${sec.symbol}</span>
                </td>
                <td class="font-mono" style="font-weight:600;font-size:0.95rem">
                    ${formatINR(sec.ltp || 0)}
                </td>
                <td class="font-mono ${changeClass}">
                    ${isPos ? '+' : ''}${sec.change ? sec.change.toFixed(2) : '0.00'}
                </td>
                <td class="font-mono ${changeClass}" style="font-weight:600">
                    ${isPos ? '▲ +' : '▼ '}${sec.change_pct ? sec.change_pct.toFixed(2) : '0.00'}%
                </td>
                <td class="font-mono text-secondary">${sec.high ? formatINR(sec.high) : '—'}</td>
                <td class="font-mono text-secondary">${sec.low ? formatINR(sec.low) : '—'}</td>
                <td class="font-mono text-muted">${formatVolume(sec.volume || 0)}</td>
                <td>
                    <span class="badge badge-accent" style="font-size:0.7rem">${(sec.index_membership || []).join(', ') || 'F&O'}</span>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="switchToOptionChain('${sec.symbol}')" style="font-size:0.75rem;padding:0.2rem 0.5rem">
                        Options
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    tableCard.innerHTML = `
        <div style="overflow-x:auto">
            <table class="table-custom">
                <thead>
                    <tr>
                        <th>Security</th>
                        <th>LTP</th>
                        <th>Change</th>
                        <th>% Change</th>
                        <th>High</th>
                        <th>Low</th>
                        <th>Volume</th>
                        <th>Index</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}

// --- Crypto Market Data ---
async function refreshCryptoMarket() {
    const [marketData, moversData, optionsData] = await Promise.all([
        fetchJSON('/api/crypto/market'),
        fetchJSON('/api/crypto/futures-movers'),
        fetchJSON('/api/crypto/options'),
    ]);

    if (marketData) {
        renderCryptoOverview(marketData);
    }
    if (moversData) {
        renderFuturesMovers(moversData);
    }
    if (optionsData) {
        renderCryptoOptions(optionsData);
    }
}

function renderCryptoOverview(data) {
    const spots = data.spots || [];
    const perpetuals = data.perpetuals || [];

    // 1. Overview Strip
    const strip = document.getElementById('crypto-ticker-strip');
    if (strip) {
        const topSymbols = [...spots, ...perpetuals].slice(0, 6);
        strip.innerHTML = topSymbols.map(item => {
            const isPos = (item.change_pct || 0) >= 0;
            const isUSD = item.symbol.includes('USD') && !item.symbol.includes('INR');
            const formattedPrice = isUSD ? `$${formatNumber(item.ltp || 0)}` : formatINR(item.ltp || 0);
            return `
                <div class="ticker-card">
                    <div class="ticker-name">${item.display_name}</div>
                    <div class="ticker-price">${formattedPrice}</div>
                    <div class="ticker-change ${isPos ? 'positive' : 'negative'}">
                        ${isPos ? '▲ +' : '▼ '}${item.change_pct ? item.change_pct.toFixed(2) : '0.00'}%
                    </div>
                </div>
            `;
        }).join('');
    }

    // 2. Crypto Spot Cards
    const spotCards = document.getElementById('crypto-spot-cards');
    if (spotCards) {
        spotCards.innerHTML = spots.map(item => {
            const isPos = (item.change_pct || 0) >= 0;
            const isUSD = item.symbol.includes('USD') && !item.symbol.includes('INR');
            return `
                <div class="card index-detail-card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:0.75rem;">
                        <div>
                            <div style="font-weight:700;font-size:1.1rem;color:var(--text-primary)">${item.display_name}</div>
                            <div class="font-mono text-muted" style="font-size:0.75rem">${item.symbol}</div>
                        </div>
                        <span class="badge badge-accent">SPOT</span>
                    </div>
                    <div style="display:flex;align-items:baseline;gap:0.75rem;margin-bottom:0.75rem;">
                        <span class="font-mono" style="font-size:1.4rem;font-weight:700;color:var(--text-primary)">
                            ${isUSD ? '$' : '₹'}${formatNumber(item.ltp || 0)}
                        </span>
                        <span class="ticker-change ${isPos ? 'positive' : 'negative'}" style="font-size:0.85rem">
                            ${isPos ? '▲ +' : '▼ '}${item.change_pct ? item.change_pct.toFixed(2) : '0.00'}%
                        </span>
                    </div>
                    <div class="grid-2 font-mono" style="font-size:0.75rem;color:var(--text-muted);border-top:1px solid var(--border-subtle);padding-top:0.5rem">
                        <div>24h High: <span class="text-green">${isUSD ? '$' : '₹'}${formatNumber(item.high_24h || 0)}</span></div>
                        <div>24h Low: <span class="text-red">${isUSD ? '$' : '₹'}${formatNumber(item.low_24h || 0)}</span></div>
                        <div>Volume: <span class="text-secondary">${formatVolume(item.volume_24h || 0)}</span></div>
                        <div>Mark: <span class="text-primary">${isUSD ? '$' : '₹'}${formatNumber(item.mark_price || item.ltp || 0)}</span></div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // 3. Perpetuals Table
    const perpsTable = document.getElementById('crypto-perpetuals-table');
    if (perpsTable) {
        const rows = perpetuals.map(perp => {
            const isPos = (perp.change_pct || 0) >= 0;
            const changeClass = isPos ? 'text-green' : 'text-red';
            const isUSD = perp.symbol.includes('USD') && !perp.symbol.includes('INR');
            return `
                <tr>
                    <td style="font-weight:600">
                        <span style="color:var(--text-primary)">${perp.display_name}</span>
                        <span class="font-mono text-muted" style="font-size:0.75rem;margin-left:0.5rem">${perp.symbol}</span>
                    </td>
                    <td class="font-mono" style="font-weight:600">${isUSD ? '$' : '₹'}${formatNumber(perp.ltp || 0)}</td>
                    <td class="font-mono ${changeClass}" style="font-weight:600">
                        ${isPos ? '▲ +' : '▼ '}${perp.change_pct ? perp.change_pct.toFixed(2) : '0.00'}%
                    </td>
                    <td class="font-mono text-cyan">${isUSD ? '$' : '₹'}${formatNumber(perp.mark_price || 0)}</td>
                    <td class="font-mono text-secondary">${(perp.funding_rate !== undefined ? (perp.funding_rate * 100).toFixed(4) : '0.0100')}%</td>
                    <td class="font-mono text-muted">${formatVolume(perp.volume_24h || 0)}</td>
                    <td class="font-mono text-primary">${formatVolume(perp.open_interest || 0)}</td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="switchToOptionChain('${perp.symbol}')" style="font-size:0.75rem;padding:0.2rem 0.5rem">
                            Options
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        perpsTable.innerHTML = `
            <div style="overflow-x:auto">
                <table class="table-custom">
                    <thead>
                        <tr>
                            <th>Contract</th>
                            <th>LTP</th>
                            <th>24h Change</th>
                            <th>Mark Price</th>
                            <th>Funding Rate (8h)</th>
                            <th>24h Volume</th>
                            <th>Open Interest</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        `;
    }
}

function renderFuturesMovers(movers) {
    const gainersCard = document.getElementById('futures-gainers');
    const losersCard = document.getElementById('futures-losers');

    if (gainersCard && movers.gainers) {
        const rows = movers.gainers.map((g, idx) => `
            <div class="mover-row">
                <div style="display:flex;align-items:center;gap:0.75rem">
                    <span class="font-mono text-muted" style="font-size:0.8rem;width:1.2rem">#${idx + 1}</span>
                    <div>
                        <div style="font-weight:600;color:var(--text-primary)">${g.display_name}</div>
                        <div class="font-mono text-muted" style="font-size:0.7rem">${g.symbol}</div>
                    </div>
                </div>
                <div style="text-align:right">
                    <div class="font-mono" style="font-weight:600">${formatNumber(g.ltp || 0)}</div>
                    <div class="font-mono text-green" style="font-weight:600;font-size:0.8rem">
                        ▲ +${g.change_pct ? g.change_pct.toFixed(2) : '0.00'}%
                    </div>
                </div>
            </div>
        `).join('');

        gainersCard.innerHTML = `
            <div class="card-header">
                <span class="card-title text-green">▲ Top 10 Gainers (Futures)</span>
            </div>
            <div class="movers-list">${rows}</div>
        `;
    }

    if (losersCard && movers.losers) {
        const rows = movers.losers.map((l, idx) => `
            <div class="mover-row">
                <div style="display:flex;align-items:center;gap:0.75rem">
                    <span class="font-mono text-muted" style="font-size:0.8rem;width:1.2rem">#${idx + 1}</span>
                    <div>
                        <div style="font-weight:600;color:var(--text-primary)">${l.display_name}</div>
                        <div class="font-mono text-muted" style="font-size:0.7rem">${l.symbol}</div>
                    </div>
                </div>
                <div style="text-align:right">
                    <div class="font-mono" style="font-weight:600">${formatNumber(l.ltp || 0)}</div>
                    <div class="font-mono text-red" style="font-weight:600;font-size:0.8rem">
                        ▼ ${l.change_pct ? l.change_pct.toFixed(2) : '0.00'}%
                    </div>
                </div>
            </div>
        `).join('');

        losersCard.innerHTML = `
            <div class="card-header">
                <span class="card-title text-red">▼ Top 10 Losers (Futures)</span>
            </div>
            <div class="movers-list">${rows}</div>
        `;
    }
}

function renderCryptoOptions(data) {
    const container = document.getElementById('crypto-options-data');
    if (!container) return;

    const underlyings = data.crypto_options || [];
    if (underlyings.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">🎯</div>
                <div class="title">No Crypto Options Available</div>
                <div class="desc">Delta Exchange options feeds will load when connected.</div>
            </div>
        `;
        return;
    }

    container.innerHTML = underlyings.map(u => {
        const optRows = (u.options || []).map(opt => `
            <tr class="${opt.is_atm ? 'oc-atm-row' : ''}">
                <td class="font-mono text-green">${formatNumber(opt.ce_premium || 0)}</td>
                <td class="font-mono text-muted">${opt.ce_delta ? opt.ce_delta.toFixed(3) : '—'}</td>
                <td class="font-mono text-secondary">${opt.ce_iv ? opt.ce_iv.toFixed(1) : '—'}%</td>
                <td class="font-mono oc-strike ${opt.is_atm ? 'text-amber font-bold' : ''}">
                    ${formatNumber(opt.strike)} ${opt.is_atm ? '★ ATM' : ''}
                </td>
                <td class="font-mono text-secondary">${opt.pe_iv ? opt.pe_iv.toFixed(1) : '—'}%</td>
                <td class="font-mono text-muted">${opt.pe_delta ? opt.pe_delta.toFixed(3) : '—'}</td>
                <td class="font-mono text-red">${formatNumber(opt.pe_premium || 0)}</td>
            </tr>
        `).join('');

        return `
            <div style="margin-bottom:1.5rem;border-bottom:1px solid var(--border-subtle);padding-bottom:1.5rem">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
                    <div>
                        <span style="font-size:1.1rem;font-weight:700;color:var(--text-primary)">${u.display_name || u.underlying} Options</span>
                        <span class="font-mono text-cyan" style="margin-left:0.75rem">Spot: ${formatNumber(u.spot || 0)}</span>
                    </div>
                    <div style="display:flex;gap:1rem;font-size:0.8rem" class="font-mono text-muted">
                        <span>Expiry: <strong class="text-primary">${u.expiry || '—'}</strong></span>
                        <span>DTE: <strong class="text-amber">${u.days_to_expiry || '—'}d</strong></span>
                    </div>
                </div>
                <div style="overflow-x:auto">
                    <table class="table-custom oc-table">
                        <thead>
                            <tr>
                                <th style="color:var(--accent-green)">Call Premium</th>
                                <th>Call Delta</th>
                                <th>Call IV</th>
                                <th style="color:var(--accent-amber)">Strike</th>
                                <th>Put IV</th>
                                <th>Put Delta</th>
                                <th style="color:var(--accent-red)">Put Premium</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${optRows}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }).join('');
}

// --- Option Chain Tab ---
async function refreshOptionChain() {
    const url = currentOcExpiry
        ? `/api/indian/option-chain/${encodeURIComponent(currentOcSymbol)}?expiry=${encodeURIComponent(currentOcExpiry)}`
        : `/api/indian/option-chain/${encodeURIComponent(currentOcSymbol)}`;
    const data = await fetchJSON(url);
    if (!data) return;

    const isUSD = currentOcSymbol.includes('USD');
    const currSym = isUSD ? '$' : '₹';
    const fmtPrice = isUSD ? (v => `$${formatNumber(v)}`) : formatINR;

    // Feed status badge
    const badgeEl = document.getElementById('oc-feed-badge');
    if (badgeEl) {
        if (data.is_real_feed) {
            badgeEl.className = 'badge badge-success';
            badgeEl.innerHTML = '🟢 Real Upstox Feed';
        } else {
            badgeEl.className = 'badge badge-warning';
            badgeEl.innerHTML = '🟡 Model Fallback (Spot-linked)';
        }
    }

    // Populate expiry selector
    const expSelect = document.getElementById('oc-expiry-select');
    if (expSelect && data.expiries && data.expiries.length > 0) {
        const optionsHtml = data.expiries.map(exp => `
            <option value="${exp}" ${exp === data.expiry ? 'selected' : ''}>${exp}</option>
        `).join('');
        // Update only if options changed to avoid jumping focus
        if (expSelect.innerHTML !== optionsHtml) {
            expSelect.innerHTML = optionsHtml;
        }
        currentOcExpiry = data.expiry;
    }

    // Info bar
    const undEl  = document.getElementById('oc-underlying');
    const spotEl = document.getElementById('oc-spot');
    const atmEl  = document.getElementById('oc-atm');
    const expEl  = document.getElementById('oc-expiry');
    const dteEl  = document.getElementById('oc-dte');
    const lotEl  = document.getElementById('oc-lotsize');

    if (undEl) undEl.textContent = data.display_name || data.symbol || currentOcSymbol;
    if (spotEl) spotEl.textContent = fmtPrice(data.spot || 0);
    if (atmEl) atmEl.textContent = fmtPrice(data.atm_strike || 0);
    if (expEl) expEl.textContent = data.expiry || '—';
    if (dteEl) dteEl.textContent = `${data.days_to_expiry ?? 0} days`;
    if (lotEl) lotEl.textContent = data.lot_size ? `${data.lot_size} units` : '1 unit';

    // Chain table
    const tableContainer = document.getElementById('option-chain-table');
    if (!tableContainer) return;

    if (!data.chain || data.chain.length === 0) {
        tableContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">📊</div>
                <div class="title">Option Chain Unavailable</div>
                <div class="desc">${data.error || 'No quotes available for ' + currentOcSymbol}</div>
            </div>
        `;
        return;
    }

    const rows = data.chain.map(item => {
        const ce = item.ce || {};
        const pe = item.pe || {};
        const isAtm = item.is_atm;

        return `
            <tr class="${isAtm ? 'oc-atm-row' : ''}">
                <td class="font-mono text-muted">${ce.oi ? formatNumber(ce.oi) : '—'}</td>
                <td class="font-mono text-muted">${ce.volume ? formatNumber(ce.volume) : '—'}</td>
                <td class="font-mono text-secondary">${ce.iv ? ce.iv.toFixed(1) : '—'}%</td>
                <td class="font-mono text-secondary">${ce.delta ? ce.delta.toFixed(3) : '—'}</td>
                <td class="font-mono text-green oc-ltp" style="font-weight:700">${currSym}${formatNumber(ce.premium || 0)}</td>
                <td class="font-mono oc-strike ${isAtm ? 'oc-atm-strike' : ''}">
                    ${fmtPrice(item.strike)} ${isAtm ? '★' : ''}
                </td>
                <td class="font-mono text-red oc-ltp" style="font-weight:700">${currSym}${formatNumber(pe.premium || 0)}</td>
                <td class="font-mono text-secondary">${pe.delta ? pe.delta.toFixed(3) : '—'}</td>
                <td class="font-mono text-secondary">${pe.iv ? pe.iv.toFixed(1) : '—'}%</td>
                <td class="font-mono text-muted">${pe.volume ? formatNumber(pe.volume) : '—'}</td>
                <td class="font-mono text-muted">${pe.oi ? formatNumber(pe.oi) : '—'}</td>
            </tr>
        `;
    }).join('');

    tableContainer.innerHTML = `
        <div style="overflow-x:auto">
            <table class="table-custom oc-table">
                <thead>
                    <tr>
                        <th colspan="5" style="text-align:center;color:var(--accent-green);border-right:1px solid var(--border-subtle)">
                            CALLS (CE)
                        </th>
                        <th style="text-align:center;color:var(--accent-amber)">STRIKE</th>
                        <th colspan="5" style="text-align:center;color:var(--accent-red);border-left:1px solid var(--border-subtle)">
                            PUTS (PE)
                        </th>
                    </tr>
                    <tr>
                        <th>OI</th>
                        <th>Volume</th>
                        <th>IV</th>
                        <th>Delta</th>
                        <th style="color:var(--accent-green)">LTP (${currSym})</th>
                        <th style="color:var(--accent-amber)">Strike</th>
                        <th style="color:var(--accent-red)">LTP (${currSym})</th>
                        <th>Delta</th>
                        <th>IV</th>
                        <th>Volume</th>
                        <th>OI</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
}

// --- Watchlist, Scan Results & Signals ---
function renderScanResults(data) {
    const container = document.getElementById('scan-results');
    const signalsList = document.getElementById('signals-list');
    if (!container) return;

    const results = data.results || [];
    if (results.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">🔍</div>
                <div class="title">No Active Setups</div>
                <div class="desc">Scanning continuous market levels. Setups will populate when detected.</div>
            </div>
        `;
        if (signalsList) {
            signalsList.innerHTML = `
                <div class="empty-state">
                    <div class="icon">🔔</div>
                    <div class="title">No Active Signals</div>
                    <div class="desc">Recent setups will appear here.</div>
                </div>
            `;
        }
        return;
    }

    // Scan results table
    const rows = results.map(r => {
        const sigCount = (r.signals || []).length;
        const sigBadge = sigCount > 0 
            ? `<span class="badge badge-accent">${sigCount} Signal${sigCount > 1 ? 's' : ''}</span>`
            : `<span class="badge badge-neutral">Scanning</span>`;

        return `
            <tr>
                <td style="font-weight:600">
                    <span style="color:var(--text-primary)">${r.symbol}</span>
                    <span class="badge badge-outline" style="font-size:0.7rem;margin-left:0.5rem">${r.exchange}</span>
                </td>
                <td class="font-mono">${r.last_price ? formatINR(r.last_price) : '—'}</td>
                <td><span class="badge badge-secondary">${r.zone_count || 0} Zones</span></td>
                <td>${sigBadge}</td>
                <td class="font-mono text-muted" style="font-size:0.75rem">${r.scan_time ? new Date(r.scan_time).toLocaleTimeString() : '—'}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="switchToOptionChain('${r.symbol}')" style="font-size:0.75rem;padding:0.2rem 0.5rem">
                        Options
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div style="overflow-x:auto">
            <table class="table-custom">
                <thead>
                    <tr>
                        <th>Instrument</th>
                        <th>Last Price</th>
                        <th>HTF Zones</th>
                        <th>Signal Status</th>
                        <th>Last Scanned</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
    `;

    // Flatten recent active signals
    if (signalsList) {
        const allSignals = [];
        results.forEach(r => {
            (r.signals || []).forEach(s => {
                allSignals.push({ ...s, symbol: r.symbol });
            });
        });

        if (allSignals.length === 0) {
            signalsList.innerHTML = `
                <div class="empty-state">
                    <div class="icon">🔔</div>
                    <div class="title">No Active Signals</div>
                    <div class="desc">Continuous level monitoring active.</div>
                </div>
            `;
        } else {
            signalsList.innerHTML = allSignals.slice(0, 5).map(s => {
                const isLong = s.direction === 'long';
                const isUSD = (s.symbol && s.symbol.endsWith('USD')) || s.exchange === 'delta';
                const fmt = isUSD ? (v => '$' + formatNumber(v)) : formatINR;
                return `
                    <div class="signal-card ${isLong ? 'long' : 'short'}" style="margin-bottom:0.75rem">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem">
                            <span style="font-weight:700;color:var(--text-primary)">${s.symbol}</span>
                            <span class="badge ${isLong ? 'badge-profit' : 'badge-loss'}">${s.direction.toUpperCase()}</span>
                        </div>
                        <div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:0.4rem">${s.reason || s.type}</div>
                        <div class="grid-3 font-mono" style="font-size:0.75rem;color:var(--text-muted)">
                            <div>Entry: <span class="text-primary">${s.entry ? fmt(s.entry) : 'Market'}</span></div>
                            <div>SL: <span class="text-red">${s.stop ? fmt(s.stop) : '—'}</span></div>
                            <div>Target: <span class="text-green">${s.target ? fmt(s.target) : '—'}</span></div>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
}

function renderZones(data) {
    const container = document.getElementById('zones-list');
    if (!container) return;

    const zones = data.zones || [];
    if (zones.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">📍</div>
                <div class="title">No Active Zones</div>
                <div class="desc">S/R zones will appear after multi-timeframe candle scans.</div>
            </div>
        `;
        return;
    }

    container.innerHTML = zones.slice(0, 8).map(z => {
        const isSupport = z.type === 'support';
        const isUSD = (z.symbol && z.symbol.endsWith('USD')) || z.exchange === 'delta';
        const fmt = isUSD ? (v => '$' + formatNumber(v)) : formatINR;
        return `
            <div class="zone-card ${isSupport ? 'support' : 'resistance'}" style="margin-bottom:0.5rem;padding:0.6rem 0.8rem;border-radius:var(--radius-sm);background:var(--bg-glass);border:1px solid var(--border-subtle)">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div>
                        <span style="font-weight:700;margin-right:0.4rem;color:var(--text-primary)">${z.symbol || ''}</span>
                        <span class="badge ${isSupport ? 'badge-profit' : 'badge-loss'}" style="font-size:0.7rem">
                            ${z.type.toUpperCase()}
                        </span>
                        <span class="font-mono" style="margin-left:0.5rem;font-weight:600">
                            ${fmt(z.low || 0)} – ${fmt(z.high || 0)}
                        </span>
                    </div>
                    <span class="font-mono text-muted" style="font-size:0.75rem">
                        Touches: ${z.touches || 1} | Str: ${(z.strength * 100).toFixed(0)}%
                    </span>
                </div>
            </div>
        `;
    }).join('');
}

// --- Positions & Performance ---
function renderPositions(data) {
    const openCard = document.getElementById('open-positions');
    const closedCard = document.getElementById('closed-trades');
    const openBadge = document.getElementById('metric-open-positions');

    const openPositions = data.open || [];
    const closedTrades = data.closed || [];

    if (openBadge) openBadge.textContent = openPositions.length;

    if (openCard) {
        if (openPositions.length === 0) {
            openCard.innerHTML = `
                <div class="empty-state">
                    <div class="icon">📭</div>
                    <div class="title">No Open Positions</div>
                    <div class="desc">Paper trades will appear here when signals are auto-executed.</div>
                </div>
            `;
        } else {
            const rows = openPositions.map(pos => {
                const isPos = (pos.unrealized_pnl || 0) >= 0;
                const isUSD = (pos.symbol && pos.symbol.endsWith('USD')) || pos.exchange === 'delta';
                const fmt = isUSD ? (v => '$' + formatNumber(v)) : formatINR;
                const execTime = formatExecutionTime(pos.execution_time || pos.entry_time);
                return `
                    <tr>
                        <td style="font-weight:600">${pos.symbol}</td>
                        <td><span class="badge ${pos.side === 'BUY' ? 'badge-profit' : 'badge-loss'}">${pos.side}</span></td>
                        <td class="font-mono">${pos.quantity}</td>
                        <td class="font-mono">${fmt(pos.entry_price || 0)}</td>
                        <td class="font-mono">${fmt(pos.current_price || pos.entry_price || 0)}</td>
                        <td class="font-mono ${isPos ? 'text-green' : 'text-red'}" style="font-weight:700">
                            ${isPos ? '+' : ''}${fmt(pos.unrealized_pnl || 0)}
                        </td>
                        <td class="font-mono text-red">${pos.stop_loss ? fmt(pos.stop_loss) : '—'}</td>
                        <td class="font-mono text-green">${(pos.take_profit || pos.target) ? fmt(pos.take_profit || pos.target) : '—'}</td>
                        <td class="font-mono" style="white-space:nowrap">${execTime}</td>
                    </tr>
                `;
            }).join('');

            openCard.innerHTML = `
                <div style="overflow-x:auto">
                    <table class="table-custom">
                        <thead>
                            <tr>
                                <th>Instrument</th>
                                <th>Side</th>
                                <th>Qty</th>
                                <th>Entry</th>
                                <th>Current</th>
                                <th>P&L</th>
                                <th>SL</th>
                                <th>TP</th>
                                <th>Execution Time</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        }
    }

    if (closedCard) {
        if (closedTrades.length === 0) {
            closedCard.innerHTML = `
                <div class="empty-state">
                    <div class="icon">📊</div>
                    <div class="title">No Closed Trades Yet</div>
                    <div class="desc">Completed trades will appear here.</div>
                </div>
            `;
        } else {
            const rows = closedTrades.map(t => {
                const isPos = (t.realized_pnl || 0) >= 0;
                const isUSD = (t.symbol && t.symbol.endsWith('USD')) || t.exchange === 'delta';
                const fmt = isUSD ? (v => '$' + formatNumber(v)) : formatINR;
                const execTime = formatExecutionTime(t.execution_time || t.entry_time);
                const closeTime = formatExecutionTime(t.closed_at || t.exit_time);
                return `
                    <tr>
                        <td style="font-weight:600">${t.symbol}</td>
                        <td><span class="badge badge-secondary">${t.side}</span></td>
                        <td class="font-mono">${fmt(t.entry_price || 0)}</td>
                        <td class="font-mono">${fmt(t.exit_price || 0)}</td>
                        <td class="font-mono ${isPos ? 'text-green' : 'text-red'}" style="font-weight:700">
                            ${isPos ? '+' : ''}${fmt(t.realized_pnl || 0)}
                        </td>
                        <td class="font-mono" style="white-space:nowrap">${execTime}</td>
                        <td class="font-mono text-muted" style="white-space:nowrap">${closeTime}</td>
                    </tr>
                `;
            }).join('');

            closedCard.innerHTML = `
                <div style="overflow-x:auto">
                    <table class="table-custom">
                        <thead>
                            <tr>
                                <th>Instrument</th>
                                <th>Side</th>
                                <th>Entry</th>
                                <th>Exit</th>
                                <th>Realized P&L</th>
                                <th>Execution Time</th>
                                <th>Closed At</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        }
    }
}

function renderPerformance(data) {
    const container = document.getElementById('performance-summary');
    if (!container) return;

    container.innerHTML = `
        <div class="grid-4" style="margin-bottom:1.5rem">
            <div class="card metric">
                <div class="metric-value font-mono ${data.total_pnl >= 0 ? 'profit' : 'loss'}">${formatINR(data.total_pnl || 0)}</div>
                <div class="metric-label">Total Realized P&L</div>
            </div>
            <div class="card metric">
                <div class="metric-value font-mono text-cyan">${(data.win_rate || 0).toFixed(1)}%</div>
                <div class="metric-label">Win Rate (${data.winning_trades || 0}W / ${data.losing_trades || 0}L)</div>
            </div>
            <div class="card metric">
                <div class="metric-value font-mono text-primary">${data.profit_factor ? data.profit_factor.toFixed(2) : '—'}</div>
                <div class="metric-label">Profit Factor</div>
            </div>
            <div class="card metric">
                <div class="metric-value font-mono text-amber">${data.total_trades || 0}</div>
                <div class="metric-label">Total Trades Taken</div>
            </div>
        </div>
    `;
}

function renderConfig(data) {
    if (!data) return;
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    setVal('cfg-starting-balance', `₹${formatNumber(data.starting_balance || 20000)}`);
    setVal('cfg-leverage', `${data.max_leverage || 3.0}x Max (Manageable)`);
    setVal('cfg-risk-per-trade', `${data.risk_per_trade_pct || 2.0}% of Capital`);
    setVal('cfg-max-positions', `${data.max_positions || 3} Positions`);
    setVal('cfg-daily-loss', `${data.max_daily_loss_pct || 5.0}% max loss`);

    if (data.options) {
        setVal('cfg-opt-capital-pct', `${data.options.max_capital_per_option_trade_pct || 45}%`);
        setVal('cfg-opt-sl-pct', `${data.options.max_sl_premium_pct || 40}% of Premium`);
    }
}

// --- Helpers & Formatting ---
function formatExecutionTime(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
        const dateStr = d.toLocaleDateString([], { day: '2-digit', month: 'short' });
        return `<span style="font-weight:600;color:var(--text-primary)">${timeStr}</span> <span class="text-secondary" style="font-size:0.75rem">${dateStr}</span>`;
    } catch (e) {
        return isoStr;
    }
}

function formatINR(val) {
    if (val === null || val === undefined || isNaN(val)) return '₹0.00';
    return '₹' + Number(val).toLocaleString('en-IN', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatNumber(val) {
    if (val === null || val === undefined || isNaN(val)) return '0.00';
    return Number(val).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatVolume(val) {
    if (!val) return '—';
    if (val >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
    if (val >= 100000) return (val / 100000).toFixed(2) + ' L';
    if (val >= 1000) return (val / 1000).toFixed(1) + ' K';
    return val.toString();
}

function flashPriceUpdate(el, newPrice, oldPrice) {
    if (!oldPrice || newPrice === oldPrice) return;
    const flashClass = newPrice > oldPrice ? 'price-flash-up' : 'price-flash-down';
    el.classList.add(flashClass);
    setTimeout(() => el.classList.remove(flashClass), 600);
}

// --- Upstox Auth & Token Refresh Management ---
function setupUpstoxAuth() {
    const refreshBtns = [
        document.getElementById('btn-header-refresh-token'),
        document.getElementById('btn-alert-refresh-token'),
        document.getElementById('btn-settings-refresh-token'),
    ];

    refreshBtns.forEach(btn => {
        if (btn) {
            btn.addEventListener('click', triggerTokenRefresh);
        }
    });
}

async function refreshUpstoxStatus() {
    const data = await fetchJSON('/api/upstox/auth-status');
    if (!data) return;

    const isActive = data.status === 'active' || (data.has_active_token && !data.last_error);
    const isConfigured = data.is_auto_login_configured;

    // 1. Header Badge
    const headerBadge = document.getElementById('upstox-token-badge');
    if (headerBadge) {
        if (isActive) {
            headerBadge.className = 'badge badge-green';
            headerBadge.textContent = '🇮🇳 Upstox: Active';
        } else {
            headerBadge.className = 'badge badge-red';
            headerBadge.textContent = '🇮🇳 Upstox: Expired (401)';
        }
    }

    // 2. Alert Banner on Indian Market Tab
    const alertBanner = document.getElementById('indian-token-alert-banner');
    if (alertBanner) {
        alertBanner.style.display = isActive ? 'none' : 'flex';
    }

    // 3. Settings Card
    const cfgStatus = document.getElementById('settings-token-status');
    if (cfgStatus) {
        if (isActive) {
            cfgStatus.className = 'badge badge-green';
            cfgStatus.textContent = 'ACTIVE (STREAMING)';
        } else {
            cfgStatus.className = 'badge badge-red';
            cfgStatus.textContent = 'EXPIRED / UNAUTHORIZED (401)';
        }
    }

    const cfgAuto = document.getElementById('settings-auto-login-cfg');
    if (cfgAuto) {
        cfgAuto.textContent = isConfigured ? 'YES (Credentials Present)' : 'NO (Missing keys in .env)';
        cfgAuto.className = isConfigured ? 'font-mono text-cyan' : 'font-mono text-amber';
    }

    const cfgUpdated = document.getElementById('settings-token-updated');
    if (cfgUpdated) {
        cfgUpdated.textContent = data.last_updated || 'Never';
    }

    const errBox = document.getElementById('settings-token-error-box');
    const errText = document.getElementById('settings-token-error-text');
    if (errBox && errText) {
        if (!isActive && data.last_error) {
            errBox.style.display = 'block';
            errText.textContent = data.last_error;
        } else {
            errBox.style.display = 'none';
        }
    }
}

async function triggerTokenRefresh() {
    const btns = [
        document.getElementById('btn-header-refresh-token'),
        document.getElementById('btn-alert-refresh-token'),
        document.getElementById('btn-settings-refresh-token'),
    ].filter(Boolean);

    btns.forEach(b => {
        b.disabled = true;
        b.style.opacity = '0.6';
    });

    const headerIcon = document.getElementById('header-refresh-icon');
    const headerText = document.getElementById('header-refresh-text');
    const settingsIcon = document.getElementById('settings-refresh-icon');
    const settingsText = document.getElementById('settings-refresh-text');

    if (headerText) headerText.textContent = 'Refreshing...';
    if (settingsText) settingsText.textContent = 'Contacting Upstox 2FA...';

    try {
        const resp = await fetch('/api/upstox/refresh-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await resp.json();

        if (data.success) {
            alert('✅ Success!\n\nUpstox access token was minted and saved successfully. Live NSE data is now streaming.');
            await refreshUpstoxStatus();
            await refreshIndianMarket();
            await refreshAll();
        } else {
            const msg = data.message || 'Auto-login failed. Please check credentials and redirect URI.';
            alert('⚠️ Upstox Token Refresh Notice:\n\n' + msg);
            await refreshUpstoxStatus();
        }
    } catch (err) {
        alert('Network error while refreshing token: ' + err.message);
    } finally {
        btns.forEach(b => {
            b.disabled = false;
            b.style.opacity = '1';
        });
        if (headerText) headerText.textContent = 'Refresh Token';
        if (settingsText) settingsText.textContent = 'Generate & Refresh Upstox Token';
    }
}

