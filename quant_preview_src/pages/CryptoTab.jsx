import { useState } from "react";
import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { fmt, get, px, tone, usd } from "@/lib/api";
import { Badge, Change, FlashPrice, MarketDisabled, Panel, SectionTitle, SkeletonRows, Stat } from "@/components/terminal/Primitives";
import { Coins, Layers, TrendingDown, TrendingUp, Zap } from "lucide-react";

const SpotCard = ({ q }) => (
  <div className="panel" style={{ borderTop: "2px solid var(--gold)" }} data-testid={`crypto-spot-${q.symbol}`}>
    <div className="panel-body">
      <div className="flex justify-between items-center"><span className="tick-name">{q.pair}</span><Change value={q.pct} /></div>
      <div className="mt-2"><FlashPrice value={q.ltp} className="tick-ltp" format={(v) => `$${px(v)}`} /></div>
      <div className="mt-2">
        <Stat k="24h High" v={`$${px(q.high_24h)}`} cls="up" /><Stat k="24h Low" v={`$${px(q.low_24h)}`} cls="down" />
        <Stat k="24h Volume" v={usd(q.volume_24h)} /><Stat k="Mark Price" v={`$${px(q.mark_price)}`} />
      </div>
    </div>
  </div>
);

const FuturesTable = ({ rows, onChain }) => (
  <Panel id="crypto-futures" title="Perpetual Futures Screener" icon={Zap} noBody sub="Funding is 8-hour rate">
    <div className="tbl-wrap" style={{ maxHeight: 520 }}>
      <table className="tbl" id="crypto-futures-table" data-testid="crypto-futures-table">
        <thead><tr><th>Contract</th><th className="r">LTP</th><th className="r">24h %</th><th className="r">Mark</th><th className="r">Funding 8h</th><th className="r">24h Vol</th><th className="r">Open Interest</th><th className="r">Options</th></tr></thead>
        <tbody>
          {!rows ? <SkeletonRows rows={8} cols={8} /> : rows.map((r) => (
            <tr key={r.contract} data-testid={`perp-row-${r.symbol}`}>
              <td className="num font-semibold" style={{ color: "var(--text-hi)" }}>{r.contract}</td>
              <td className="r"><FlashPrice value={r.ltp} /></td>
              <td className="r"><Change value={r.pct} showIcon={false} /></td>
              <td className="r num muted">{px(r.mark_price)}</td>
              <td className={`r num ${tone(r.funding_rate)}`}>{fmt(r.funding_rate, 4)}%</td>
              <td className="r num muted">{usd(r.volume_24h)}</td>
              <td className="r num">{usd(r.open_interest)}</td>
              <td className="r">
                <button className="btn btn-xs btn-cyan" onClick={() => onChain(r.symbol)} data-testid={`perp-options-btn-${r.symbol}`}>Options</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Panel>
);

const Movers = ({ id, title, icon, rows, up }) => (
  <Panel id={id} title={title} icon={icon} noBody>
    <table className="tbl" data-testid={`${id}-table`}>
      <tbody>
        {!rows ? <SkeletonRows rows={10} cols={3} /> : rows.map((r, i) => (
          <tr key={r.contract}>
            <td className="num dim" style={{ width: 36 }}>#{i + 1}</td>
            <td className="num font-semibold">{r.contract}</td>
            <td className="r num">{px(r.ltp)}</td>
            <td className="r"><Badge tone={up ? "up" : "down"}>{r.pct > 0 ? "+" : ""}{fmt(r.pct)}%</Badge></td>
          </tr>
        ))}
      </tbody>
    </table>
  </Panel>
);

const OptionsDeck = ({ decks }) => {
  const [u, setU] = useState("BTC");
  const deck = decks?.find((d) => d.underlying === u);
  const right = (
    <div className="seg" data-testid="crypto-options-underlying">
      {["BTC", "ETH", "SOL"].map((x) => <button key={x} className={u === x ? "active" : ""} onClick={() => setU(x)} data-testid={`crypto-options-${x}`}>{x}</button>)}
    </div>
  );
  return (
    <Panel id="crypto-options-deck" title="Crypto Options Deck (USD)" icon={Coins} right={right} noBody
      sub={deck && `Spot $${px(deck.spot)} · Expiry ${deck.expiry} · DTE ${fmt(deck.dte, 2)}`}>
      {deck && (
        <div className="flex gap-4 px-4 pt-3 text-xs num muted" data-testid="crypto-options-meta">
          <span>Spot <b style={{ color: "var(--text-hi)" }}>${px(deck.spot)}</b></span><span>Expiry <b>{deck.expiry}</b></span><span>DTE <b>{fmt(deck.dte, 2)}</b></span>
        </div>
      )}
      <div className="tbl-wrap">
        <table className="tbl chain-table" data-testid="crypto-options-table">
          <thead><tr><th className="r">Call Prem</th><th className="r">Delta</th><th className="r">IV</th><th className="c">Strike</th><th className="r">Put IV</th><th className="r">Put Delta</th><th className="r">Put Prem</th></tr></thead>
          <tbody>
            {!deck ? <SkeletonRows rows={9} cols={7} /> : deck.rows.map((r) => (
              <tr key={r.strike} className={r.is_atm ? "atm" : ""}>
                <td className="r up">${px(r.call_premium)}</td><td className="r">{fmt(r.call_delta, 3)}</td><td className="r muted">{fmt(r.call_iv, 1)}%</td>
                <td className="strike">{r.is_atm && "★ "}{px(r.strike)}</td>
                <td className="r muted">{fmt(r.put_iv, 1)}%</td><td className="r">{fmt(r.put_delta, 3)}</td><td className="r down">${px(r.put_premium)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

export default function CryptoTab() {
  const { toggles, setMarket, openChain } = useTerminal();
  const on = toggles.crypto;
  const { data: m } = usePoll(() => get("/crypto/market"), [], { enabled: on });
  const { data: mv } = usePoll(() => get("/crypto/futures-movers"), [], { enabled: on });
  const { data: op } = usePoll(() => get("/crypto/options"), [], { enabled: on, interval: 10000 });
  if (!on) {
    return (
      <div className="am-stack">
        <SectionTitle title="₿ Crypto Market" sub="Spot, perpetual futures and USD options" />
        <MarketDisabled market="Crypto Market" id="crypto-disabled-banner" onEnable={() => setMarket("crypto", true)} />
      </div>
    );
  }
  return (
    <div className="am-stack">
      <SectionTitle title="₿ Crypto Market" sub="Spot, perpetual futures and USD options" />
      <div className="am-grid" id="crypto-spot-grid" data-testid="crypto-spot-grid">
        {(m?.spot || Array.from({ length: 6 })).map((q, i) => (
          <div key={q?.symbol || i} className="col-span-12 sm:col-span-6 lg:col-span-4 2xl:col-span-2">{q ? <SpotCard q={q} /> : <div className="skel h-[200px]" />}</div>
        ))}
      </div>
      <div className="am-grid">
        <div className="col-span-12"><FuturesTable rows={m?.perpetuals} onChain={openChain} /></div>
        <div className="col-span-12 md:col-span-6"><Movers id="futures-gainers" title="Top 10 Gainers" icon={TrendingUp} rows={mv?.gainers} up /></div>
        <div className="col-span-12 md:col-span-6"><Movers id="futures-losers" title="Top 10 Losers" icon={TrendingDown} rows={mv?.losers} /></div>
      </div>
      <OptionsDeck decks={op?.decks} />
      <div className="text-xs dim flex items-center gap-2"><Layers size={12} />Open any underlying in the full Option Chain viewer via its Options button.</div>
    </div>
  );
}
