import { useMemo, useState } from "react";
import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { get, money, signedMoney, tone, px, timeStr, label, BULLISH_SETUPS } from "@/lib/api";
import { Badge, Change, EmptyRow, FlashPrice, Panel, SkeletonRows } from "./Primitives";
import { CandleChart } from "./CandleChart";
import { Briefcase, CandlestickChart, ChevronDown, ChevronUp, Crosshair, Radar, Repeat, Target, Wallet } from "lucide-react";

const Kpi = ({ id, label: l, icon: Icon, value, foot, accent, cls = "" }) => (
  <div className="panel kpi h-full" style={{ "--accent": accent }} data-testid={`${id}-card`}>
    <div className="kpi-label"><Icon size={13} style={{ color: accent }} />{l}</div>
    <div className={`kpi-value ${cls}`} id={id} data-testid={id}>{value ?? <span className="skel inline-block h-6 w-28" />}</div>
    <div className="kpi-foot analytic-only">{foot}</div>
  </div>
);

export const KpiGrid = ({ b }) => (
  <div className="am-grid h-full" data-testid="kpi-grid">
    <div className="col-span-12 sm:col-span-6 xl:col-span-3">
      <Kpi id="metric-balance" label="Portfolio Balance" icon={Wallet} accent="var(--indigo)" value={b && money(b.balance)}
        foot={b && `Equity ${money(b.equity)} · Free ${money(b.available)}`} />
    </div>
    <div className="col-span-12 sm:col-span-6 xl:col-span-3">
      <Kpi id="metric-daily-pnl" label="Today's Realized P&L" icon={Target} accent={b?.daily_pnl >= 0 ? "var(--up)" : "var(--down)"}
        value={b && signedMoney(b.daily_pnl)} cls={b ? `${tone(b.daily_pnl)} glow-${b.daily_pnl >= 0 ? "up" : "down"}` : ""}
        foot={b && `${b.daily_pnl_pct > 0 ? "+" : ""}${b.daily_pnl_pct}% · Unrealized ${signedMoney(b.unrealized_pnl)}`} />
    </div>
    <div className="col-span-12 sm:col-span-6 xl:col-span-3">
      <Kpi id="metric-open-positions" label="Open Positions" icon={Briefcase} accent="var(--cyan)" value={b && `${b.open_positions} / 3`}
        foot={b && `Margin used ${money(b.used_margin)}`} />
    </div>
    <div className="col-span-12 sm:col-span-6 xl:col-span-3">
      <Kpi id="metric-trade-count" label="Today's Trades" icon={Repeat} accent="var(--saffron)" value={b && b.today_trades}
        foot="Closed executions since 09:15 IST" />
    </div>
  </div>
);

export const TickerCard = ({ q, brand, onClick, testid }) => (
  <button className="tick-card text-left" style={{ "--brand": brand }} onClick={onClick} data-testid={testid}>
    <div className="flex justify-between items-center gap-2">
      <span className="tick-name truncate">{q.name || q.pair}</span>
      <Change value={q.pct} showIcon={false} />
    </div>
    <div className="flex justify-between items-baseline gap-2 mt-1">
      <FlashPrice value={q.ltp} className="tick-ltp" />
      <span className={`num text-xs ${tone(q.change)}`}>{q.change > 0 ? "+" : ""}{px(q.change)}</span>
    </div>
  </button>
);

export const TickerStrip = ({ id, items, brand, onPick, enabled }) => (
  <div className="ticker-strip" id={id} data-testid={id}>
    {!enabled ? <div className="banner banner-off col-span-full text-xs">Feed disabled</div>
      : !items ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="skel h-[62px]" />)
        : items.map((q) => <TickerCard key={q.symbol} q={q} brand={brand} onClick={() => onPick(q.symbol)} testid={`${id}-${q.symbol}`} />)}
  </div>
);

const Collapse = ({ open, onClick }) => (
  <button className="btn btn-xs" onClick={onClick} data-testid="chart-collapse-btn">
    {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}{open ? "Collapse" : "Expand"}
  </button>
);

export const ChartPanel = () => {
  const { chartSymbol, setChartSymbol, catalog } = useTerminal();
  const [open, setOpen] = useState(true);
  const { data: pos } = usePoll(() => get("/positions"), []);
  const active = pos?.open.find((p) => p.symbol === chartSymbol);
  const levels = useMemo(() => active?.chart_levels, [active?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const right = (
    <>
      <select className="am-select" value={chartSymbol} onChange={(e) => setChartSymbol(e.target.value)} id="chart-symbol-select" data-testid="chart-symbol-select">
        <optgroup label="Indices">{catalog.indices.map((x) => <option key={x.symbol} value={x.symbol}>{x.symbol}</option>)}</optgroup>
        <optgroup label="Indian F&O Equities">{catalog.stocks.map((x) => <option key={x.symbol} value={x.symbol}>{x.symbol}</option>)}</optgroup>
        <optgroup label="Crypto">{catalog.crypto.map((x) => <option key={x.symbol} value={x.symbol}>{x.symbol}</option>)}</optgroup>
      </select>
      <Collapse open={open} onClick={() => setOpen(!open)} />
    </>
  );
  return (
    <Panel id="chart-panel" title={`${chartSymbol} · 5m Candles · 4h S/R Zones`} icon={CandlestickChart} right={right}
      sub="TradingView Lightweight Charts — zone bands from /api/zones, trade levels from the active position" bodyClass="!p-0">
      {open && (
        <>
          <div className="flex flex-wrap gap-4 px-4 pt-3" data-testid="chart-legend">
            <span className="legend-chip"><b style={{ background: "rgba(16,185,129,0.35)" }} />Support zone</span>
            <span className="legend-chip"><b style={{ background: "rgba(244,63,94,0.35)" }} />Resistance zone</span>
            {active ? (
              <>
                <span className="legend-chip"><i style={{ borderColor: "#a5b4fc" }} />Entry {px(levels?.entry)}</span>
                <span className="legend-chip"><i style={{ borderColor: "#f43f5e" }} />SL {px(levels?.stop_loss)}</span>
                <span className="legend-chip"><i style={{ borderColor: "#10b981" }} />Target {px(levels?.target)}</span>
                <Badge tone="indigo" testid="chart-active-trade">{active.instrument} · {active.side}</Badge>
              </>
            ) : <span className="legend-chip dim">No active trade on {chartSymbol}</span>}
          </div>
          <CandleChart symbol={chartSymbol} levels={levels} />
        </>
      )}
    </Panel>
  );
};

export const signalTone = (s) => (s === "no_signal" ? "" : BULLISH_SETUPS.includes(s) ? "up" : s === "approaching_zone" ? "amber" : "down");

export const ScanTable = () => {
  const { openChain, openChart } = useTerminal();
  const { data } = usePoll(() => get("/scan-results"), []);
  return (
    <Panel id="market-watchlist" title="Market Watchlist & Scan Results" icon={Radar} noBody
      sub="Multi-timeframe scanner — HTF 4h zones, 5m trigger setups">
      <div className="tbl-wrap" style={{ maxHeight: 440 }}>
        <table className="tbl" id="scan-results" data-testid="scan-results">
          <thead><tr><th>Instrument</th><th>Exch</th><th className="r">Last Price</th><th className="r">Chg %</th><th className="c">HTF Zones</th><th>Signal Status</th><th>Last Scanned</th><th className="r">Actions</th></tr></thead>
          <tbody>
            {!data ? <SkeletonRows cols={8} /> : data.results.map((r) => (
              <tr key={r.symbol} data-testid={`scan-row-${r.symbol}`}>
                <td><div className="font-semibold num" style={{ color: "var(--text-hi)" }}>{r.symbol}</div><div className="dim text-[11px] analytic-only">{r.name}</div></td>
                <td><Badge tone={r.exchange === "NSE" ? "saffron" : "gold"}>{r.exchange}</Badge></td>
                <td className="r"><FlashPrice value={r.ltp} /></td>
                <td className="r"><Change value={r.pct} showIcon={false} /></td>
                <td className="c"><Badge tone="indigo">{r.zones_count}</Badge></td>
                <td><Badge tone={signalTone(r.signal_status)}>{label(r.signal_status)}</Badge></td>
                <td className="num dim">{timeStr(r.last_scanned)}</td>
                <td className="r">
                  <div className="inline-flex gap-1">
                    <button className="btn btn-xs" onClick={() => openChart(r.symbol)} data-testid={`scan-chart-btn-${r.symbol}`}>Chart</button>
                    <button className="btn btn-xs btn-cyan" onClick={() => openChain(r.symbol)} data-testid={`scan-options-btn-${r.symbol}`}>Options</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

export const ZonesTable = () => {
  const { chartSymbol } = useTerminal();
  const [scope, setScope] = useState("chart");
  const { data } = usePoll(() => get("/zones", scope === "chart" ? { symbol: chartSymbol } : {}), [scope, chartSymbol]);
  const right = (
    <div className="seg" data-testid="zones-scope">
      <button className={scope === "chart" ? "active" : ""} onClick={() => setScope("chart")} data-testid="zones-scope-chart">{chartSymbol}</button>
      <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} data-testid="zones-scope-all">All</button>
    </div>
  );
  return (
    <Panel id="active-zones" title="Active S/R Zones (4h)" icon={Crosshair} noBody right={right}>
      <div className="tbl-wrap" style={{ maxHeight: 360 }}>
        <table className="tbl" data-testid="zones-table">
          <thead><tr><th>Instrument</th><th>Type</th><th className="r">Low</th><th className="r">High</th><th>Strength</th><th className="c">Touches</th></tr></thead>
          <tbody>
            {!data ? <SkeletonRows cols={6} /> : data.zones.length === 0 ? <EmptyRow cols={6} text="No zones" /> : data.zones.map((z) => (
              <tr key={z.id}>
                <td className="num">{z.symbol}</td>
                <td><Badge tone={z.type === "support" ? "up" : "down"}>{z.type}</Badge></td>
                <td className="r num">{px(z.price_low)}</td>
                <td className="r num">{px(z.price_high)}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <div className="gauge-track" style={{ width: 60, height: 5 }}><div className="gauge-fill" style={{ width: `${z.strength}%`, background: "var(--indigo)" }} /></div>
                    <span className="num">{z.strength}%</span>
                  </div>
                </td>
                <td className="c num">{z.touches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

export const SignalsTable = () => {
  const { data } = usePoll(() => get("/signals"), []);
  return (
    <Panel id="live-signals" title="Live Signals" icon={Target} noBody right={data && <Badge tone="cyan">{data.signals.length} signals</Badge>}>
      <div className="tbl-wrap" style={{ maxHeight: 360 }}>
        <table className="tbl" data-testid="signals-table">
          <thead><tr><th>Time</th><th>Instrument</th><th>Setup</th><th>Dir</th><th className="r">Entry</th><th className="r">Stop-Loss</th><th className="r">Target</th><th className="r">R:R</th></tr></thead>
          <tbody>
            {!data ? <SkeletonRows cols={8} /> : data.signals.map((s) => (
              <tr key={s.id} data-testid={`signal-row-${s.id}`}>
                <td className="num dim">{timeStr(s.timestamp)}</td>
                <td className="num font-semibold">{s.symbol}</td>
                <td><Badge tone={signalTone(s.setup)}>{label(s.setup)}</Badge></td>
                <td><Badge tone={s.direction === "BUY" ? "up" : "down"}>{s.direction}</Badge></td>
                <td className="r num">{px(s.entry)}</td>
                <td className="r num down">{px(s.stop_loss)}</td>
                <td className="r num up">{px(s.target)}</td>
                <td className="r num">1:{s.rr}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};
