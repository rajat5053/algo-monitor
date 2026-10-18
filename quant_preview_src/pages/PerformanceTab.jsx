import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { usePoll } from "@/hooks/usePoll";
import { fmt, get, money, signedMoney, tone } from "@/lib/api";
import { Panel, SectionTitle } from "@/components/terminal/Primitives";
import { BarChart3, LineChart, Percent, Scale, Sigma } from "lucide-react";

const SEGS = [["all", "All Trades"], ["intraday", "Intraday Trades"], ["swing", "Swing Trades"]];

const Card = ({ id, label, icon: Icon, value, foot, cls = "", accent }) => (
  <div className="col-span-12 sm:col-span-6 xl:col-span-3">
    <div className="panel kpi" style={{ "--accent": accent }}>
      <div className="kpi-label"><Icon size={13} style={{ color: accent }} />{label}</div>
      <div className={`kpi-value ${cls}`} id={id} data-testid={id}>{value}</div>
      <div className="kpi-foot">{foot}</div>
    </div>
  </div>
);

const Summary = ({ b }) => (
  <div className="am-grid" id="performance-summary" data-testid="performance-summary">
    <Card id="perf-total-pnl" label="Total Realized P&L" icon={Sigma} value={signedMoney(b.total_pnl)} cls={tone(b.total_pnl)} accent="var(--up)" foot={`Best ${money(b.best)} · Worst ${money(b.worst)}`} />
    <Card id="perf-win-rate" label="Win Rate" icon={Percent} value={`${fmt(b.win_rate, 1)}%`} accent="var(--cyan)" foot={<span data-testid="perf-win-loss">{b.wins}W / {b.losses}L</span>} />
    <Card id="perf-profit-factor" label="Profit Factor" icon={Scale} value={b.profit_factor == null ? "∞" : fmt(b.profit_factor, 2)} accent="var(--indigo)" foot={`Avg win ${money(b.avg_win)} · Avg loss ${money(b.avg_loss)}`} />
    <Card id="perf-total-trades" label="Total Trades" icon={BarChart3} value={b.total_trades} accent="var(--saffron)" foot="Closed paper executions" />
  </div>
);

const ROWS = [
  ["Total P&L", (b) => signedMoney(b.total_pnl), (b) => tone(b.total_pnl)], ["Trades", (b) => b.total_trades],
  ["Wins / Losses", (b) => `${b.wins} / ${b.losses}`], ["Win Rate", (b) => `${fmt(b.win_rate, 1)}%`],
  ["Profit Factor", (b) => (b.profit_factor == null ? "∞" : fmt(b.profit_factor, 2))], ["Avg Win", (b) => money(b.avg_win), () => "up"],
  ["Avg Loss", (b) => money(b.avg_loss), () => "down"], ["Best Trade", (b) => money(b.best)], ["Worst Trade", (b) => money(b.worst)],
];

const Breakdown = ({ d }) => (
  <Panel id="performance-breakdown" title="Stratified Reports" icon={BarChart3} noBody>
    <div className="tbl-wrap">
      <table className="tbl" data-testid="performance-breakdown-table">
        <thead><tr><th>Metric</th>{SEGS.map(([k, l]) => <th key={k} className="r">{l}</th>)}</tr></thead>
        <tbody>
          {ROWS.map(([l, f, c]) => (
            <tr key={l}><td className="muted">{l}</td>{SEGS.map(([k]) => <td key={k} className={`r num ${c ? c(d[k]) : ""}`}>{f(d[k])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  </Panel>
);

const Equity = ({ curve }) => (
  <Panel id="equity-curve" title="Equity Curve" icon={LineChart}>
    <div style={{ height: 290 }} data-testid="equity-curve-chart">
      <ResponsiveContainer>
        <AreaChart data={curve.map((c) => ({ ...c, t: new Date(c.time).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) }))}>
          <defs><linearGradient id="eq" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#6366f1" stopOpacity={0.45} /><stop offset="100%" stopColor="#6366f1" stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis dataKey="t" stroke="#64748b" fontSize={10} tickLine={false} />
          <YAxis stroke="#64748b" fontSize={10} tickLine={false} domain={["auto", "auto"]} width={60} />
          <Tooltip contentStyle={{ background: "#0b1222", border: "1px solid rgba(255,255,255,0.1)", fontFamily: "JetBrains Mono", fontSize: 11 }} formatter={(v) => money(v)} />
          <Area dataKey="equity" stroke="#818cf8" strokeWidth={2} fill="url(#eq)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </Panel>
);

export default function PerformanceTab() {
  const { data } = usePoll(() => get("/performance"), [], { interval: 15000 });
  const [seg, setSeg] = useState("all");
  return (
    <div className="am-stack">
      <SectionTitle title="Analytics & Performance" sub="Realized results across trading styles (INR-equivalent)" />
      <div className="seg self-start" data-testid="perf-segments">
        {SEGS.map(([k, l]) => <button key={k} className={seg === k ? "active" : ""} onClick={() => setSeg(k)} data-testid={`perf-seg-${k}`}>{l}</button>)}
      </div>
      {!data ? <div className="skel h-40" /> : (
        <>
          <Summary b={data[seg]} />
          <div className="am-grid">
            <div className="col-span-12 xl:col-span-7"><Equity curve={data.equity_curve} /></div>
            <div className="col-span-12 xl:col-span-5"><Breakdown d={data} /></div>
          </div>
        </>
      )}
    </div>
  );
}
