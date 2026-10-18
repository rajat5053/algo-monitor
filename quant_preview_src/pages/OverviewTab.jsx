import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { get } from "@/lib/api";
import { SectionTitle } from "@/components/terminal/Primitives";
import { RiskGauge } from "@/components/terminal/RiskGauge";
import { ChartPanel, KpiGrid, ScanTable, SignalsTable, TickerStrip, ZonesTable } from "@/components/terminal/OverviewParts";

export default function OverviewTab() {
  const { toggles, openChart } = useTerminal();
  const { data: bal } = usePoll(() => get("/balance"), []);
  const { data: idx } = usePoll(() => get("/indian/indices"), [], { enabled: toggles.indian });
  const { data: cm } = usePoll(() => get("/crypto/market"), [], { enabled: toggles.crypto });
  return (
    <div className="am-stack">
      <SectionTitle title="Overview" sub="Portfolio telemetry, live tickers, scanner and HTF structure at a glance." />
      <div className="am-grid">
        <div className="col-span-12 2xl:col-span-9"><KpiGrid b={bal} /></div>
        <div className="col-span-12 2xl:col-span-3"><RiskGauge balance={bal} id="risk-gauge-overview" /></div>
      </div>
      <div className="am-grid">
        <div className="col-span-12 xl:col-span-6">
          <div className="panel-title mb-2" style={{ color: "var(--saffron)" }}>🇮🇳 NSE Indices</div>
          <TickerStrip id="index-ticker-strip" items={idx?.items} brand="var(--saffron)" onPick={openChart} enabled={toggles.indian} />
        </div>
        <div className="col-span-12 xl:col-span-6">
          <div className="panel-title mb-2" style={{ color: "var(--gold)" }}>₿ Crypto Spot & Perps</div>
          <TickerStrip id="crypto-ticker-strip" items={cm?.spot.slice(0, 4)} brand="var(--gold)" onPick={openChart} enabled={toggles.crypto} />
        </div>
      </div>
      <ChartPanel />
      <ScanTable />
      <div className="am-grid">
        <div className="col-span-12 xl:col-span-5"><ZonesTable /></div>
        <div className="col-span-12 xl:col-span-7"><SignalsTable /></div>
      </div>
    </div>
  );
}
