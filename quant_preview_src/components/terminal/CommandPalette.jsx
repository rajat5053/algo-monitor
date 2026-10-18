import { useEffect } from "react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { useTerminal } from "@/context/TerminalContext";
import { TABS } from "./TabsNav";
import { Bell, CandlestickChart, Layers, LayoutGrid, Power, RefreshCw } from "lucide-react";

const isTyping = (e) => ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || e.target.isContentEditable;

function useHotkeys() {
  const t = useTerminal();
  useEffect(() => {
    const onKey = (e) => {
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "k") {
        e.preventDefault();
        t.setPaletteOpen(!t.paletteOpen);
      } else if (k === "/" && !isTyping(e) && !t.paletteOpen) {
        e.preventDefault();
        t.setPaletteOpen(true);
      } else if (e.altKey && /^[1-7]$/.test(e.key)) {
        e.preventDefault();
        t.setTab(TABS[Number(e.key) - 1].id);
      } else if (e.altKey && k === "i") {
        t.setMarket("indian", !t.toggles.indian);
      } else if (e.altKey && k === "c") {
        t.setMarket("crypto", !t.toggles.crypto);
      } else if (e.altKey && k === "r") {
        t.refreshToken();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [t]);
}

const Item = ({ value, onSelect, icon: Icon, children, hint, testid }) => (
  <CommandItem value={value} onSelect={onSelect} data-testid={testid}>
    {Icon && <Icon size={14} />}{children}{hint && <span className="palette-item-hint">{hint}</span>}
  </CommandItem>
);

export const CommandPalette = () => {
  const t = useTerminal();
  useHotkeys();
  const run = (fn) => () => {
    t.setPaletteOpen(false);
    fn();
  };
  const all = [...t.catalog.indices, ...t.catalog.stocks, ...t.catalog.crypto];
  return (
    <CommandDialog open={t.paletteOpen} onOpenChange={t.setPaletteOpen}>
      <CommandInput placeholder="Search ticker, jump to option chain, or run a command…" data-testid="omnibar-input" />
      <CommandList className="max-h-[420px]" data-testid="omnibar-list">
        <CommandEmpty>No matches.</CommandEmpty>
        <CommandGroup heading="Commands">
          <Item value="cmd toggle indian market" icon={Power} hint="Alt+I" onSelect={run(() => t.setMarket("indian", !t.toggles.indian))} testid="omnibar-cmd-toggle-indian">
            {t.toggles.indian ? "Disable" : "Enable"} Indian Market feed
          </Item>
          <Item value="cmd toggle crypto market" icon={Power} hint="Alt+C" onSelect={run(() => t.setMarket("crypto", !t.toggles.crypto))} testid="omnibar-cmd-toggle-crypto">
            {t.toggles.crypto ? "Disable" : "Enable"} Crypto Market feed
          </Item>
          <Item value="cmd refresh upstox token" icon={RefreshCw} hint="Alt+R" onSelect={run(t.refreshToken)} testid="omnibar-cmd-refresh-token">Refresh Upstox Token</Item>
          <Item value="cmd density pro analytical" icon={LayoutGrid} onSelect={run(() => t.setDensity(t.density === "pro" ? "analytical" : "pro"))} testid="omnibar-cmd-density">
            Switch to {t.density === "pro" ? "Analytical" : "Pro Terminal"} mode
          </Item>
          <Item value="cmd audio chime" icon={Bell} onSelect={run(() => t.setAudio(!t.audio))} testid="omnibar-cmd-audio">{t.audio ? "Mute" : "Unmute"} alert chime</Item>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Navigate">
          {TABS.map((tab, i) => (
            <Item key={tab.id} value={`go ${tab.label}`} icon={tab.icon} hint={`Alt+${i + 1}`} onSelect={run(() => t.setTab(tab.id))} testid={`omnibar-nav-${tab.id}`}>{tab.label}</Item>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Option Chain">
          {all.map((x) => (
            <Item key={`oc-${x.symbol}`} value={`chain ${x.symbol} ${x.name}`} icon={Layers} hint="chain" onSelect={run(() => t.openChain(x.symbol))} testid={`omnibar-chain-${x.symbol}`}>
              <span className="num">{x.symbol}</span><span className="dim text-xs">{x.name}</span>
            </Item>
          ))}
        </CommandGroup>
        <CommandGroup heading="Chart">
          {all.map((x) => (
            <Item key={`ch-${x.symbol}`} value={`chart ${x.symbol} ${x.name}`} icon={CandlestickChart} hint="chart" onSelect={run(() => t.openChart(x.symbol))} testid={`omnibar-chart-${x.symbol}`}>
              <span className="num">{x.symbol}</span><span className="dim text-xs">{x.name}</span>
            </Item>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
};
