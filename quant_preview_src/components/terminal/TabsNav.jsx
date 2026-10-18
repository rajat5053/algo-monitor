import { useTerminal } from "@/context/TerminalContext";
import { Activity, BarChart3, Bitcoin, Briefcase, Gauge, Layers, Settings } from "lucide-react";

export const TABS = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "indian", label: "Indian Market", icon: Activity, flag: "🇮🇳" },
  { id: "crypto", label: "Crypto Market", icon: Bitcoin },
  { id: "optionchain", label: "Option Chain", icon: Layers },
  { id: "positions", label: "Positions & Orders", icon: Briefcase },
  { id: "performance", label: "Analytics & Performance", icon: BarChart3 },
  { id: "settings", label: "Settings & Risk Rules", icon: Settings },
];

export const TabsNav = () => {
  const { tab, setTab } = useTerminal();
  return (
    <nav className="am-tabs" id="tab-nav" data-testid="tab-nav" role="tablist">
      {TABS.map((t, i) => (
        <button key={t.id} role="tab" aria-selected={tab === t.id} data-tab={t.id} id={`tab-btn-${t.id}`}
          data-testid={`tab-btn-${t.id}`} className={`tab-btn ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
          <t.icon size={14} />
          {t.label}
          <span className="tab-idx analytic-only">{i + 1}</span>
        </button>
      ))}
    </nav>
  );
};
