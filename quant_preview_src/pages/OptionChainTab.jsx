import { useEffect, useMemo, useRef, useState } from "react";
import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { compact, fmt, get, INDEX_SYMBOLS, isCrypto, px } from "@/lib/api";
import { Badge, Panel, SectionTitle, SkeletonRows } from "@/components/terminal/Primitives";
import { TokenAlert } from "@/pages/IndianTab";
import { Gauge, Layers, Scale, Target } from "lucide-react";

export function chainAnalytics(strikes) {
  if (!strikes?.length) return null;
  const sum = (f) => strikes.reduce((a, s) => a + f(s), 0);
  const cOi = sum((s) => s.ce.oi), pOi = sum((s) => s.pe.oi);
  const cV = sum((s) => s.ce.volume), pV = sum((s) => s.pe.volume);
  let maxPain = null, best = Infinity;
  strikes.forEach(({ strike: K }) => {
    const pain = sum((s) => s.ce.oi * Math.max(0, K - s.strike) + s.pe.oi * Math.max(0, s.strike - K));
    if (pain < best) { best = pain; maxPain = K; }
  });
  const oiPcr = pOi / cOi;
  const sentiment = oiPcr > 1.2 ? "Bullish" : oiPcr < 0.8 ? "Bearish" : "Neutral";
  const maxOi = Math.max(...strikes.flatMap((s) => [s.ce.oi, s.pe.oi]));
  return { cOi, pOi, cV, pV, oiPcr, volPcr: pV / cV, maxPain, sentiment, maxOi };
}

const Controls = ({ data, expiry, setExpiry }) => {
  const { chainSymbol, setChainSymbol, catalog } = useTerminal();
  const [parent, setParent] = useState(INDEX_SYMBOLS.includes(chainSymbol) ? chainSymbol : null);
  const [cons, setCons] = useState([]);
  useEffect(() => {
    if (INDEX_SYMBOLS.includes(chainSymbol)) setParent(chainSymbol);
    else if (!cons.some((c) => c.symbol === chainSymbol)) setParent(null);
  }, [chainSymbol]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!parent) { setCons([]); return; }
    get("/indian/index-constituents", { index: parent }).then((d) => setCons(d.constituents)).catch(() => setCons([]));
  }, [parent]);
  const feed = data?.feed;
  return (
    <div className="panel panel-body flex flex-wrap items-center gap-3" id="oc-controls" data-testid="oc-controls">
      <label className="text-xs muted">Instrument</label>
      <select className="am-select" id="oc-symbol" data-testid="oc-symbol" value={parent && chainSymbol !== parent ? parent : chainSymbol}
        onChange={(e) => setChainSymbol(e.target.value)}>
        <optgroup label="Indices">{catalog.indices.map((x) => <option key={x.symbol} value={x.symbol}>{x.symbol} — {x.name}</option>)}</optgroup>
        <optgroup label="Indian F&O Equities">{catalog.stocks.map((x) => <option key={x.symbol} value={x.symbol}>{x.symbol}</option>)}</optgroup>
        <optgroup label="Crypto Underlyings">{["BTCUSD", "ETHUSD", "SOLUSD"].map((x) => <option key={x} value={x}>{x}</option>)}</optgroup>
      </select>
      {parent && cons.length > 0 && (
        <>
          <label className="text-xs muted">Constituent</label>
          <select className="am-select" id="oc-constituent" data-testid="oc-constituent" value={chainSymbol} onChange={(e) => setChainSymbol(e.target.value)}>
            <option value={parent}>— {parent} (index) —</option>
            {cons.map((c) => <option key={c.symbol} value={c.symbol}>{c.symbol} · {c.name}</option>)}
          </select>
        </>
      )}
      <label className="text-xs muted">Expiry</label>
      <select className="am-select" id="oc-expiry" data-testid="oc-expiry" value={expiry || data?.expiry || ""} onChange={(e) => setExpiry(e.target.value)}>
        {(data?.expiries || []).map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <span className="ml-auto" id="oc-feed-status" data-testid="oc-feed-status">
        {feed && <Badge tone={feed === "model" ? "amber" : "up"}>{feed === "upstox" ? "🟢 Real Upstox Feed" : feed === "exchange" ? "🟢 Live Exchange Feed" : "🟡 Model Fallback · Black-Scholes"}</Badge>}
      </span>
    </div>
  );
};

const Tele = ({ k, v, testid, cls = "" }) => (
  <div className="min-w-[110px]"><div className="text-[10.5px] uppercase tracking-wider dim">{k}</div><div className={`num text-sm font-semibold ${cls}`} style={{ color: cls ? undefined : "var(--text-hi)" }} data-testid={testid}>{v}</div></div>
);

const AnalyticsBar = ({ data, a }) => {
  const callPct = (a.cOi / (a.cOi + a.pOi)) * 100;
  const sTone = a.sentiment === "Bullish" ? "up" : a.sentiment === "Bearish" ? "down" : "amber";
  return (
    <div className="am-grid" id="oc-analytics" data-testid="oc-analytics">
      <div className="col-span-12 lg:col-span-7 panel panel-body flex flex-wrap content-center gap-x-8 gap-y-3" id="oc-telemetry" data-testid="oc-telemetry">
        <Tele k="Underlying" v={data.symbol} testid="oc-tele-symbol" /><Tele k="Spot" v={px(data.spot)} testid="oc-tele-spot" />
        <Tele k="ATM Strike" v={px(data.atm_strike)} testid="oc-tele-atm" /><Tele k="Expiry" v={data.expiry} testid="oc-tele-expiry" />
        <Tele k="DTE" v={fmt(data.dte, 2)} testid="oc-tele-dte" /><Tele k="Lot Size" v={data.lot_size} testid="oc-tele-lot" />
      </div>
      <div className="col-span-6 lg:col-span-2 panel panel-body">
        <div className="panel-title"><Scale size={13} />PCR</div>
        <div className="flex gap-5 mt-2">
          <Tele k="OI PCR" v={fmt(a.oiPcr, 2)} testid="oc-oi-pcr" /><Tele k="Vol PCR" v={fmt(a.volPcr, 2)} testid="oc-volume-pcr" />
        </div>
      </div>
      <div className="col-span-6 lg:col-span-3 panel panel-body">
        <div className="flex justify-between items-center">
          <div className="panel-title"><Target size={13} />Max Pain</div>
          <span className="bdg bdg-indigo num" id="oc-max-pain" data-testid="oc-max-pain">{px(a.maxPain)}</span>
        </div>
        <div className="flex justify-between text-[10.5px] mt-3 num"><span className="up">CE OI {compact(a.cOi)}</span><span className="down">PE OI {compact(a.pOi)}</span></div>
        <div className="oi-dist mt-1" id="oc-oi-bar" data-testid="oc-oi-bar">
          <div style={{ width: `${callPct}%`, background: "var(--up)" }} /><div style={{ width: `${100 - callPct}%`, background: "var(--down)" }} />
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs muted"><Gauge size={12} />Sentiment <span className={`bdg bdg-${sTone}`} data-testid="oc-sentiment">{a.sentiment}</span></div>
      </div>
    </div>
  );
};

const OiCell = ({ v, max, side }) => (
  <td className="r oi-cell">
    <div className="oi-bar" style={{ width: `${(v / max) * 100}%`, [side === "ce" ? "right" : "left"]: 0, background: side === "ce" ? "var(--up)" : "var(--down)" }} />
    <span>{compact(v)}</span>
  </td>
);

const ChainTable = ({ data, a }) => {
  const wrap = useRef(null);
  const key = `${data.symbol}-${data.expiry}`;
  const scrolled = useRef("");
  useEffect(() => {
    if (scrolled.current === key) return;
    scrolled.current = key;
    const row = wrap.current?.querySelector("tr.atm");
    if (row) wrap.current.scrollTop = row.offsetTop - wrap.current.clientHeight / 2;
  }, [key]);
  const p = (v) => (data.currency === "USD" ? `$${px(v)}` : fmt(v, 2));
  return (
    <Panel id="option-chain-panel" title={`${data.symbol} Option Chain · ${data.expiry}`} icon={Layers} noBody>
      <div className="tbl-wrap" style={{ maxHeight: 620 }} ref={wrap}>
        <table className="tbl chain-table" id="option-chain-table" data-testid="option-chain-table">
          <thead>
            <tr className="chain-group"><th colSpan={5} style={{ color: "var(--up)" }}>CALLS (CE)</th><th /><th colSpan={5} style={{ color: "var(--down)" }}>PUTS (PE)</th></tr>
            <tr><th className="r">OI</th><th className="r">Volume</th><th className="r">IV</th><th className="r">Delta</th><th className="r">LTP</th><th className="c">Strike</th><th className="r">LTP</th><th className="r">Delta</th><th className="r">IV</th><th className="r">Volume</th><th className="r">OI</th></tr>
          </thead>
          <tbody>
            {data.strikes.map((s) => {
              const ci = s.strike < data.spot ? "itm-c" : "", pi = s.strike > data.spot ? "itm-p" : "";
              return (
                <tr key={s.strike} className={s.is_atm ? "atm" : ""} data-testid={`oc-row-${s.strike}`}>
                  <OiCell v={s.ce.oi} max={a.maxOi} side="ce" />
                  <td className={`r muted ${ci}`}>{compact(s.ce.volume)}</td><td className={`r muted ${ci}`}>{fmt(s.ce.iv, 1)}</td>
                  <td className={`r ${ci}`}>{fmt(s.ce.delta, 3)}</td><td className={`r up font-semibold ${ci}`}>{p(s.ce.ltp)}</td>
                  <td className="strike">{s.is_atm && <span style={{ color: "var(--amber)" }}>★ </span>}{px(s.strike)}{s.strike === a.maxPain && <span className="bdg bdg-indigo ml-1" style={{ fontSize: 8.5, padding: "0 4px" }}>MP</span>}</td>
                  <td className={`r down font-semibold ${pi}`}>{p(s.pe.ltp)}</td><td className={`r ${pi}`}>{fmt(s.pe.delta, 3)}</td>
                  <td className={`r muted ${pi}`}>{fmt(s.pe.iv, 1)}</td><td className={`r muted ${pi}`}>{compact(s.pe.volume)}</td>
                  <OiCell v={s.pe.oi} max={a.maxOi} side="pe" />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

export default function OptionChainTab() {
  const { chainSymbol } = useTerminal();
  const [expiry, setExpiry] = useState("");
  useEffect(() => setExpiry(""), [chainSymbol]);
  const fetcher = () => isCrypto(chainSymbol)
    ? get("/crypto/options", { symbol: chainSymbol, expiry: expiry || undefined })
    : get(`/indian/option-chain/${encodeURIComponent(chainSymbol)}`, { expiry: expiry || undefined });
  const { data: raw } = usePoll(fetcher, [chainSymbol, expiry]);
  const data = raw && raw.symbol === chainSymbol ? raw : null;
  const a = useMemo(() => chainAnalytics(data?.strikes), [data]);
  return (
    <div className="am-stack">
      <SectionTitle title="📊 Option Chain" sub="Symmetric strike matrix with PCR, Max Pain and OI distribution" />
      {!isCrypto(chainSymbol) && <TokenAlert />}
      <Controls data={data} expiry={expiry} setExpiry={setExpiry} />
      {!data || !a ? (
        <div className="panel"><table className="tbl"><tbody><SkeletonRows rows={12} cols={11} /></tbody></table></div>
      ) : (
        <>
          <AnalyticsBar data={data} a={a} />
          <ChainTable data={data} a={a} />
        </>
      )}
    </div>
  );
}
