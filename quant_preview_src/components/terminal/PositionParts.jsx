import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fmt, px } from "@/lib/api";
import { ThumbsDown, ThumbsUp } from "lucide-react";

const REC = {
  HOLD_CURRENT_PLAN: ["Hold Plan", "indigo"],
  CONSIDER_TARGET_EXTENSION: ["Extend Target", "up"],
  CONSIDER_PROFIT_TAKING: ["Take Profit", "amber"],
  CONSIDER_STOP_TIGHTENING: ["Tighten Stop", "cyan"],
  EXIT_THESIS_INVALIDATED: ["Exit · Invalidated", "down"],
  MONITORING_UNAVAILABLE: ["Monitoring N/A", "muted"],
  TRAIL_STOP: ["Trail Stop", "cyan"],
  TAKE_PROFIT_EARLY: ["Take Profit Early", "amber"],
  EXIT_AT_STOP: ["Stop Breached · Exit", "down"],
};

export const RProgress = ({ adv, testid }) => {
  if (!adv) return <div style={{ minWidth: 190 }} className="dim text-[11px]">—</div>;
  const targetR = Number(adv.target_r) || 1.5;
  const rAchieved = Number(adv.r_achieved) || 0;
  const progressPct = Number(adv.progress_to_target_pct) || 0;
  const T = Math.max(targetR, 1.01);
  const pos = (x) => ((Math.max(-1, Math.min(T, x)) + 1) / (T + 1)) * 100;
  const e = pos(0), cur = pos(adv.r_achieved);
  const color = adv.r_achieved < 0 ? "var(--down)" : adv.progress_to_target_pct >= 75 ? "var(--amber)" : "var(--up)";
  return (
    <div style={{ minWidth: 190 }} data-testid={testid}>
      <div className="flex justify-between text-[10.5px] num mb-1.5">
        <span style={{ color }} data-testid={`${testid}-r`}>{adv.r_achieved > 0 ? "+" : ""}{fmt(adv.r_achieved, 2)}R</span>
        <span className="dim">{fmt(adv.progress_to_target_pct, 0)}% to target</span>
      </div>
      <div className="rtrack">
        <div className="rfill" style={{ left: `${Math.min(e, cur)}%`, width: `${Math.abs(cur - e)}%`, background: `linear-gradient(90deg, ${adv.r_achieved < 0 ? "var(--down), #fb7185" : `var(--up), ${color}`})` }} />
        <span className="rmark stop" style={{ left: 0 }} />
        <span className="rmark entry" style={{ left: `${e}%` }} />
        <span className="rmark" style={{ left: `${pos(1)}%` }} />
        <span className="rmark target" style={{ left: "calc(100% - 2px)" }} />
        <span className="rnow" style={{ left: `${cur}%`, background: color }} />
      </div>
      <div className="rlabels">
        <span style={{ left: "2%" }}>SL</span><span style={{ left: `${e}%` }}>0R</span>
        <span style={{ left: `${pos(1)}%` }}>1R</span><span style={{ left: "94%" }}>{fmt(T, 1)}R</span>
      </div>
    </div>
  );
};

export const AdvisoryBadge = ({ adv, testid }) => {
  if (!adv) return <span className="dim text-[11px]">—</span>;
  const rec = adv.recommendation || "HOLD_CURRENT_PLAN";
  const [l, t] = REC[rec] || [rec.replace(/_/g, " "), "indigo"];
  const evFor = Array.isArray(adv.evidence_for) ? adv.evidence_for : [];
  const evAgainst = Array.isArray(adv.evidence_against) ? adv.evidence_against : [];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button className={`bdg bdg-${t || "indigo"} cursor-help`} data-testid={testid}>{l}</button>
      </TooltipTrigger>
      <TooltipContent side="left" className="max-w-[300px] p-3" style={{ background: "#0b1222", border: "1px solid rgba(255,255,255,0.12)" }}>
        <div className="text-[11px] font-semibold mb-2 num" style={{ color: "var(--text-hi)" }}>{rec} · Eval. target {px(adv.evaluated_target)}</div>
        {evFor.map((x) => <div key={x} className="flex gap-1.5 text-[11px] up"><ThumbsUp size={11} className="mt-0.5 shrink-0" />{x}</div>)}
        {evAgainst.map((x) => <div key={x} className="flex gap-1.5 text-[11px] down mt-0.5"><ThumbsDown size={11} className="mt-0.5 shrink-0" />{x}</div>)}
      </TooltipContent>
    </Tooltip>
  );
};

export const REC_LABEL = REC;
