import { useState } from "react";
import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { compact, get, px, tone } from "@/lib/api";
import { Badge, Change, FlashPrice, MarketDisabled, Panel, SectionTitle, SkeletonRows, Stat } from "@/components/terminal/Primitives";
import { AlertTriangle, Filter, Layers, RefreshCw } from "lucide-react";

const FILTERS = [["ALL", "All"], ["NIFTY50", "Nifty 50"], ["BANKNIFTY", "Bank Nifty"], ["NIFTYAUTO", "Nifty Auto"], ["MIDCPNIFTY", "Midcap Select"]];
const IDX_LABEL = Object.fromEntries(FILTERS);

export const TokenAlert = () => {
  const { auth, refreshToken, refreshing } = useTerminal();
  if (!auth || auth.valid) return null;
  return (
    <div className="banner banner-warn" id="upstox-token-alert" data-testid="upstox-token-alert">
      <div className="flex items-center gap-3">
        <AlertTriangle size={18} />
        <div>
          <div className="font-semibold">Upstox access token expired</div>
          <div className="text-xs opacity-80">{auth.error} Option chains fall back to the Black-Scholes model.</div>
        </div>
      </div>
      <button className="btn btn-primary" onClick={refreshToken} disabled={refreshing} id="btn-refresh-token-now" data-testid="btn-refresh-token-now">
        <RefreshCw size={13} className={refreshing ? "spin" : ""} />Refresh Token Now
      </button>
    </div>
  );
};

const IndexCard = ({ q, onChain }) => {
  const span = q.high - q.low || 1;
  const pos = ((q.ltp - q.low) / span) * 100;
  return (
    <div className="panel" style={{ borderTop: "2px solid var(--saffron)" }} data-testid={`index-card-${q.symbol}`}>
      <div className="panel-body">
        <div className="flex justify-between items-start gap-2">
          <div><div className="tick-name">{q.name}</div><div className="num dim text-[11px]">{q.symbol} · Lot {q.lot_size}</div></div>
          <button className="btn btn-xs btn-cyan" onClick={() => onChain(q.symbol)} data-testid={`btn-chain-${q.symbol}`}><Layers size={11} />Chain</button>
        </div>
        <div className="flex items-baseline gap-3 mt-3">
          <FlashPrice value={q.ltp} className="tick-ltp" testid={`index-ltp-${q.symbol}`} />
          <span className={`num text-sm ${tone(q.change)}`}>{q.change > 0 ? "+" : ""}{px(q.change)}</span>
          <Change value={q.pct} />
        </div>
        <div className="gauge-track mt-3" style={{ height: 4 }} title="Intraday range">
          <div className="gauge-fill" style={{ width: `${Math.min(100, Math.max(2, pos))}%`, background: "linear-gradient(90deg, var(--down), var(--up))" }} />
        </div>
        <div className="mt-3">
          <Stat k="Open" v={px(q.open)} /><Stat k="Day High" v={px(q.high)} cls="up" />
          <Stat k="Day Low" v={px(q.low)} cls="down" /><Stat k="Prev Close" v={px(q.prev_close)} />
        </div>
      </div>
    </div>
  );
};

const FnoTable = ({ onChain }) => {
  const [filter, setFilter] = useState("ALL");
  const { data } = usePoll(() => get("/indian/fno-securities", { index: filter }), [filter]);
  const pills = (
    <div className="flex gap-1.5 flex-wrap" id="fno-filters" data-testid="fno-filters">
      {FILTERS.map(([k, l]) => (
        <button key={k} data-filter={k} className={`pill ${filter === k ? "active" : ""}`} onClick={() => setFilter(k)} data-testid={`fno-filter-${k}`}>{l}</button>
      ))}
    </div>
  );
  return (
    <Panel id="fno-screener" title="F&O Securities Screener" icon={Filter} right={pills} noBody sub={data && `${data.count} securities`}>
      <div className="tbl-wrap" style={{ maxHeight: 560 }}>
        <table className="tbl" id="fno-table" data-testid="fno-table">
          <thead><tr><th>Security</th><th>Symbol</th><th className="r">LTP</th><th className="r">Change</th><th className="r">% Chg</th><th className="r">High</th><th className="r">Low</th><th className="r">Volume</th><th>Index</th><th className="r">Options</th></tr></thead>
          <tbody>
            {!data ? <SkeletonRows rows={8} cols={10} /> : data.items.map((s) => (
              <tr key={s.symbol} data-testid={`fno-row-${s.symbol}`}>
                <td style={{ color: "var(--text-hi)" }}>{s.name}</td>
                <td className="num muted">{s.symbol}</td>
                <td className="r"><FlashPrice value={s.ltp} /></td>
                <td className={`r num ${tone(s.change)}`}>{s.change > 0 ? "+" : ""}{px(s.change)}</td>
                <td className="r"><Change value={s.pct} showIcon={false} /></td>
                <td className="r num">{px(s.high)}</td>
                <td className="r num">{px(s.low)}</td>
                <td className="r num muted">{compact(s.volume)}</td>
                <td><div className="flex gap-1">{s.indices.map((i) => <Badge key={i} tone="saffron">{IDX_LABEL[i]}</Badge>)}</div></td>
                <td className="r"><button className="btn btn-xs btn-cyan" onClick={() => onChain(s.symbol)} data-testid={`fno-options-btn-${s.symbol}`}>Options</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

export default function IndianTab() {
  const { toggles, setMarket, openChain } = useTerminal();
  const { data } = usePoll(() => get("/indian/indices"), [], { enabled: toggles.indian });
  return (
    <div className="am-stack">
      <SectionTitle title="🇮🇳 Indian Market" sub="NSE indices and F&O universe · Upstox feed" />
      <TokenAlert />
      {!toggles.indian ? <MarketDisabled market="Indian Market" id="indian-disabled-banner" onEnable={() => setMarket("indian", true)} /> : (
        <>
          <div className="am-grid" id="indian-indices-grid" data-testid="indian-indices-grid">
            {(data?.items || Array.from({ length: 4 })).map((q, i) => (
              <div key={q?.symbol || i} className="col-span-12 sm:col-span-6 xl:col-span-3">
                {q ? <IndexCard q={q} onChain={openChain} /> : <div className="skel h-[260px]" />}
              </div>
            ))}
          </div>
          <FnoTable onChain={openChain} />
        </>
      )}
    </div>
  );
}
