import { useTerminal } from "@/context/TerminalContext";
import { Zap } from "lucide-react";
import { MarketToggles, SafetyBar, UpstoxCapsule, ViewControls } from "./HeaderParts";
import { TabsNav } from "./TabsNav";

export const Header = () => {
  const { toggles } = useTerminal();
  const scope = [toggles.indian && "NSE F&O", toggles.crypto && "Crypto Perps"].filter(Boolean).join(" + ") || "All feeds paused";
  return (
    <div className="am-top" data-testid="app-header">
      <header className="am-header">
        <div className="brand">
          <div className="brand-mark"><Zap size={18} fill="currentColor" /></div>
          <div className="min-w-0">
            <h1 id="app-title" data-testid="app-title">Algo Monitor</h1>
            <p id="market-scope-subtitle" data-testid="market-scope-subtitle">
              Live Markets · Options · Paper Trading
              <span className="scope-chip" id="market-scope" data-testid="market-scope">{scope}</span>
            </p>
          </div>
        </div>
        <div className="header-cluster"><MarketToggles /><UpstoxCapsule /></div>
        <div className="header-cluster"><SafetyBar /><ViewControls /></div>
      </header>
      <TabsNav />
    </div>
  );
};
