import { Panel } from "./Primitives";
import { fmt, money } from "@/lib/api";
import { ShieldAlert } from "lucide-react";

const level = (p) =>
  p >= 100 ? ["TRIPPED", "var(--down)", "bdg-down"]
    : p >= 80 ? ["CRITICAL", "var(--down)", "bdg-down"]
      : p >= 50 ? ["CAUTION", "var(--amber)", "bdg-amber"]
        : ["SAFE", "var(--up)", "bdg-up"];

export const RiskGauge = ({ balance, id }) => {
  const used = balance?.daily_loss_used ?? 0;
  const limit = balance?.daily_loss_limit ?? 1000;
  const p = Math.min(100, (used / limit) * 100);
  const [state, color, cls] = level(p);
  return (
    <Panel id={id} testid={id} title="Daily Risk Circuit Breaker" icon={ShieldAlert}
      sub="Today's loss vs. the maximum daily loss threshold"
      right={<span className={`bdg ${cls}`} data-testid={`${id}-state`}>{state}</span>}>
      {balance == null ? <div className="skel h-16" /> : (
        <>
          <div className="flex items-baseline justify-between gap-3">
            <div className="num" style={{ fontSize: "var(--kpi-fs)", fontWeight: 600, color }} data-testid={`${id}-used`}>
              {money(used)} <span className="dim" style={{ fontSize: 13 }}>/ {money(limit, "INR", 0)}</span>
            </div>
            <div className="num muted text-xs" data-testid={`${id}-pct`}>
              {fmt(balance.daily_loss_used_pct)}% / {fmt(balance.daily_loss_limit_pct, 1)}%
            </div>
          </div>
          <div className="gauge-track mt-3">
            <div className="gauge-fill" style={{ width: `${Math.max(p, 1.5)}%`, background: `linear-gradient(90deg, var(--up), ${color})` }} />
            <span className="gauge-tick" style={{ left: "50%" }} />
            <span className="gauge-tick" style={{ left: "80%" }} />
          </div>
          <div className="flex justify-between mt-2 num dim" style={{ fontSize: 10 }}>
            <span>₹0</span><span>50% caution</span><span>80% critical</span><span>{money(limit, "INR", 0)}</span>
          </div>
          {p >= 50 && (
            <div className="mt-3 text-xs" style={{ color }} data-testid={`${id}-alert`}>
              {p >= 100 ? "Circuit breaker tripped — new entries blocked for today." : `Risk budget ${fmt(p, 0)}% consumed — reduce size or stand aside.`}
            </div>
          )}
        </>
      )}
    </Panel>
  );
};
