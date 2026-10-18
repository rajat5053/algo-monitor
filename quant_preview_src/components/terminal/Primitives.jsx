import { useFlash } from "@/hooks/usePoll";
import { pct, px, tone } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, PowerOff } from "lucide-react";

export const Panel = ({ title, icon: Icon, sub, right, children, id, testid, className = "", bodyClass = "" , noBody }) => (
  <section id={id} data-testid={testid || id} className={`panel ${className}`}>
    {title && (
      <div className="panel-head">
        <div>
          <div className="panel-title">{Icon && <Icon size={14} />}{title}</div>
          {sub && <div className="panel-sub analytic-only">{sub}</div>}
        </div>
        {right && <div className="flex items-center gap-2 flex-wrap">{right}</div>}
      </div>
    )}
    {noBody ? children : <div className={`panel-body ${bodyClass}`}>{children}</div>}
  </section>
);

export const Badge = ({ tone: t = "", children, testid, title }) => (
  <span className={`bdg ${t ? `bdg-${t}` : ""}`} data-testid={testid} title={title}>{children}</span>
);

export const Change = ({ value, showIcon = true, testid }) => (
  <span className={`num ${tone(value)} inline-flex items-center gap-0.5`} data-testid={testid}>
    {showIcon && value > 0 && <ArrowUpRight size={12} />}
    {showIcon && value < 0 && <ArrowDownRight size={12} />}
    {pct(value)}
  </span>
);

export const FlashPrice = ({ value, className = "", testid, format = px }) => {
  const flash = useFlash(value);
  return (
    <span className={`num rounded px-1 -mx-1 ${flash} ${className}`} data-testid={testid}>{format(value)}</span>
  );
};

export const SkeletonRows = ({ rows = 5, cols = 6 }) => (
  <>
    {Array.from({ length: rows }).map((_, i) => (
      <tr key={i}>
        {Array.from({ length: cols }).map((__, j) => (
          <td key={j}><div className="skel h-3 w-full max-w-[90px]" /></td>
        ))}
      </tr>
    ))}
  </>
);

export const EmptyRow = ({ cols, text }) => (
  <tr><td colSpan={cols} className="text-center dim" style={{ padding: 28 }}>{text}</td></tr>
);

export const SectionTitle = ({ title, sub }) => (
  <div className="section-title"><h2>{title}</h2><p>{sub}</p></div>
);

export const MarketDisabled = ({ market, onEnable, id }) => (
  <div className="banner banner-off" id={id} data-testid={id}>
    <div className="flex items-center gap-3">
      <PowerOff size={18} />
      <div>
        <div className="font-semibold" style={{ color: "var(--text-hi)" }}>{market} feed is switched off</div>
        <div className="text-xs">Scanning, quotes and signals for this market are paused. Toggle it back on to resume polling.</div>
      </div>
    </div>
    <button className="btn btn-primary" onClick={onEnable} data-testid={`${id}-enable-btn`}>Enable {market}</button>
  </div>
);

export const Stat = ({ k, v, testid, cls = "" }) => (
  <div className="stat-row"><span className="k">{k}</span><span className={`v ${cls}`} data-testid={testid}>{v}</span></div>
);
