import { useState } from "react";
import { usePoll } from "@/hooks/usePoll";
import { dateTimeStr, fmt, get, money, px, signedMoney, tone } from "@/lib/api";
import { Badge, EmptyRow, FlashPrice, Panel, SectionTitle, SkeletonRows, Stat } from "@/components/terminal/Primitives";
import { AdvisoryBadge, REC_LABEL, RProgress } from "@/components/terminal/PositionParts";
import { CandleChart } from "@/components/terminal/CandleChart";
import { Brain, Briefcase, CandlestickChart, History, ThumbsDown, ThumbsUp } from "lucide-react";

const OpenTable = ({ rows, sel, setSel }) => (
  <Panel id="open-positions-panel" title="Open Positions" icon={Briefcase} noBody sub="Live-enriched with current price, unrealized P&L and R-multiple progress — click a row to chart it"
    right={rows && <Badge tone="cyan">{rows.length} open</Badge>}>
    <div className="tbl-wrap">
      <table className="tbl" id="open-positions" data-testid="open-positions">
        <thead><tr><th>Instrument</th><th>Side</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Current</th><th className="r">Unrealized P&L</th><th className="r">Stop Loss</th><th className="r">Target</th><th>R-Multiple Track</th><th>Advisory</th><th>Executed</th></tr></thead>
        <tbody>
          {!rows ? <SkeletonRows cols={11} /> : rows.length === 0 ? <EmptyRow cols={11} text="No open positions" /> : rows.map((p) => (
            <tr key={p.id} className={`cursor-pointer ${sel === p.id ? "selected" : ""}`} onClick={() => setSel(p.id)} data-testid={`position-row-${p.symbol}`}>
              <td><div className="num font-semibold" style={{ color: "var(--text-hi)" }}>{p.instrument}</div><div className="dim text-[11px] analytic-only">{p.trade_type} · {p.setup.replace(/_/g, " ")}</div></td>
              <td><Badge tone={p.side === "BUY" ? "up" : "down"}>{p.side}</Badge></td>
              <td className="r num">{p.qty}</td>
              <td className="r num">{px(p.entry)}</td>
              <td className="r"><FlashPrice value={p.current_price} /></td>
              <td className={`r num font-semibold ${tone(p.unrealized_pnl)}`} data-testid={`position-pnl-${p.symbol}`}>{signedMoney(p.unrealized_pnl, p.currency)}</td>
              <td className="r num down">{px(p.stop_loss)}</td>
              <td className="r num up">{px(p.target)}</td>
              <td><RProgress adv={p.advisory} testid={`r-progress-${p.symbol}`} /></td>
              <td><AdvisoryBadge adv={p.advisory} testid={`advisory-badge-${p.symbol}`} /></td>
              <td className="num dim">{dateTimeStr(p.opened_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Panel>
);

const AdvisoryCard = ({ p }) => {
  const a = p.advisory;
  const [l, t] = REC_LABEL[a.recommendation];
  return (
    <div className="panel panel-body" data-testid={`advisory-card-${p.symbol}`}>
      <div className="flex justify-between items-center gap-2"><span className="num font-semibold" style={{ color: "var(--text-hi)" }}>{p.instrument}</span><Badge tone={t}>{l}</Badge></div>
      <div className="mt-2">
        <Stat k="R achieved (r_achieved)" v={`${fmt(a.r_achieved, 2)}R`} cls={tone(a.r_achieved)} />
        <Stat k="Progress to target" v={`${fmt(a.progress_to_target_pct, 1)}%`} />
        <Stat k="Recommendation" v={a.recommendation} />
        <Stat k="Evaluated target" v={px(a.evaluated_target)} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-[11.5px]">
        <div><div className="dim uppercase text-[10px] tracking-wider mb-1">Evidence for</div>{a.evidence_for.map((x) => <div key={x} className="flex gap-1.5 up"><ThumbsUp size={11} className="mt-0.5 shrink-0" />{x}</div>)}</div>
        <div><div className="dim uppercase text-[10px] tracking-wider mb-1">Evidence against</div>{a.evidence_against.map((x) => <div key={x} className="flex gap-1.5 down"><ThumbsDown size={11} className="mt-0.5 shrink-0" />{x}</div>)}</div>
      </div>
    </div>
  );
};

const ClosedTable = ({ rows }) => (
  <Panel id="closed-trades-panel" title="Closed Trades History" icon={History} noBody>
    <div className="tbl-wrap" style={{ maxHeight: 460 }}>
      <table className="tbl" id="closed-trades" data-testid="closed-trades">
        <thead><tr><th>Instrument</th><th>Side</th><th className="r">Qty</th><th className="r">Entry</th><th className="r">Exit</th><th className="r">Realized P&L</th><th>Exit</th><th>Type</th><th>Executed</th><th>Closed</th></tr></thead>
        <tbody>
          {!rows ? <SkeletonRows cols={10} /> : rows.map((t) => (
            <tr key={t.id} data-testid={`closed-row-${t.id}`}>
              <td className="num font-semibold">{t.instrument}</td>
              <td><Badge tone={t.side === "BUY" ? "up" : "down"}>{t.side}</Badge></td>
              <td className="r num">{t.qty}</td><td className="r num">{px(t.entry)}</td><td className="r num">{px(t.exit)}</td>
              <td className={`r num font-semibold ${tone(t.pnl)}`}>{signedMoney(t.pnl, t.currency)}</td>
              <td><Badge tone={t.exit_reason === "TARGET" ? "up" : "down"}>{t.exit_reason.replace("_", " ")}</Badge></td>
              <td className="muted">{t.trade_type}</td>
              <td className="num dim">{dateTimeStr(t.opened_at)}</td><td className="num dim">{dateTimeStr(t.closed_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Panel>
);

export default function PositionsTab() {
  const { data } = usePoll(() => get("/positions"), []);
  const [sel, setSel] = useState(null);
  const active = data?.open.find((p) => p.id === sel) || data?.open[0];
  const total = data?.open.reduce((s, p) => s + p.unrealized_pnl_inr, 0);
  return (
    <div className="am-stack">
      <SectionTitle title="Positions & Orders" sub={data ? `Net unrealized ${money(total)} (INR-equivalent)` : "Loading…"} />
      <OpenTable rows={data?.open} sel={active?.id} setSel={setSel} />
      {active && (
        <Panel id="position-chart" title={`${active.symbol} · ${active.instrument} — Entry / SL / Target`} icon={CandlestickChart} bodyClass="!p-0">
          <CandleChart symbol={active.symbol} levels={active.chart_levels} height={320} testid="position-candle-chart" />
        </Panel>
      )}
      <Panel id="trade-advisory" title="Adaptive Target & Trade Management Advisory (P3-A)" icon={Brain} sub="Engine re-evaluates structure every poll">
        <div className="am-grid">
          {(data?.open || []).map((p) => <div key={p.id} className="col-span-12 lg:col-span-4"><AdvisoryCard p={p} /></div>)}
        </div>
      </Panel>
      <ClosedTable rows={data?.closed} />
    </div>
  );
}
