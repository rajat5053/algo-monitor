import "@/App.css";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { TerminalProvider, useTerminal } from "@/context/TerminalContext";
import { Header } from "@/components/terminal/Header";
import { CommandPalette } from "@/components/terminal/CommandPalette";
import OverviewTab from "@/pages/OverviewTab";
import IndianTab from "@/pages/IndianTab";
import CryptoTab from "@/pages/CryptoTab";
import OptionChainTab from "@/pages/OptionChainTab";
import PositionsTab from "@/pages/PositionsTab";
import PerformanceTab from "@/pages/PerformanceTab";
import SettingsTab from "@/pages/SettingsTab";

const VIEWS = {
  overview: OverviewTab, indian: IndianTab, crypto: CryptoTab, optionchain: OptionChainTab,
  positions: PositionsTab, performance: PerformanceTab, settings: SettingsTab,
};

const Main = () => {
  const { tab } = useTerminal();
  const View = VIEWS[tab];
  return (
    <main className="am-main">
      <div key={tab} id={`tab-${tab}`} data-testid={`tab-panel-${tab}`} className="tab-enter tab-content active" role="tabpanel">
        <View />
      </div>
    </main>
  );
};

function App() {
  return (
    <TerminalProvider>
      <TooltipProvider delayDuration={120}>
        <div className="am-shell">
          <Header />
          <Main />
          <footer className="am-footer" data-testid="app-footer">
            <span>Algo Monitor v3 · Paper trading only — no live orders are ever routed.</span>
            <span className="num">SIMULATED (MOCKED) MARKET DATA · Ctrl+K command palette · Alt+1–7 tabs</span>
          </footer>
        </div>
        <CommandPalette />
        <Toaster theme="dark" position="bottom-right" richColors closeButton
          toastOptions={{ style: { background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", fontFamily: "Inter" } }} />
      </TooltipProvider>
    </TerminalProvider>
  );
}

export default App;
