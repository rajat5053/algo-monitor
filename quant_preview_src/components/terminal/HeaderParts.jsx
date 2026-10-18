import { useTerminal } from "@/context/TerminalContext";
import { useNow } from "@/hooks/usePoll";
import { Bell, BellOff, Command, KeyRound, LayoutGrid, Rows3, RefreshCw, ShieldCheck } from "lucide-react";

const Toggle = ({ id, label, flag, on, onChange, cls }) => (
  <label className="capsule cursor-pointer" style={{ paddingRight: 10 }} htmlFor={id}>
    <span>{flag}</span>
    <span className="hide-sm" style={{ color: on ? "var(--text-hi)" : "var(--dim)" }}>{label}</span>
    <button id={id} data-testid={id} role="switch" aria-checked={on} aria-label={label}
      className={`am-switch ${cls}`} onClick={() => onChange(!on)} />
  </label>
);

export const MarketToggles = () => {
  const { toggles, setMarket } = useTerminal();
  return (
    <div className="flex items-center gap-2" data-testid="market-toggles">
      <Toggle id="toggle-indian" label="Indian Market" flag="🇮🇳" cls="saffron" on={toggles.indian} onChange={(v) => setMarket("indian", v)} />
      <Toggle id="toggle-crypto" label="Crypto Market" flag="₿" cls="gold" on={toggles.crypto} onChange={(v) => setMarket("crypto", v)} />
    </div>
  );
};

const remaining = (s) => (s > 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : `${Math.floor(s / 60)}m`);

export const UpstoxCapsule = () => {
  const { auth, refreshing, refreshToken } = useTerminal();
  const valid = auth?.valid;
  return (
    <div className="capsule" data-testid="upstox-capsule">
      <KeyRound size={13} style={{ color: valid ? "var(--up)" : "var(--amber)" }} />
      <span id="upstox-token-badge" data-testid="upstox-token-badge" data-valid={valid ? "true" : "false"}
        className={`bdg ${auth == null ? "" : valid ? "bdg-up" : "bdg-amber"}`}
        title={auth?.expires_at ? `Expires ${new Date(auth.expires_at).toLocaleString()}` : ""}>
        {auth == null ? "Upstox · …" : valid ? `Upstox · Valid ${remaining(auth.seconds_remaining)}` : "Upstox · Expired"}
      </span>
      <button id="btn-header-refresh-token" data-testid="btn-header-refresh-token" className="btn btn-xs btn-icon"
        onClick={refreshToken} disabled={refreshing} title="Refresh Upstox token (Alt+R)">
        <RefreshCw size={13} className={refreshing ? "spin" : ""} />
      </button>
    </div>
  );
};

export const SafetyBar = () => {
  const { connected, lastUpdate } = useTerminal();
  const now = useNow();
  const ago = lastUpdate ? Math.max(0, Math.round((now - lastUpdate.getTime()) / 1000)) : null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="bdg bdg-cyan" id="paper-trading-badge" data-testid="paper-trading-badge"><ShieldCheck size={11} />Paper Trading Only</span>
      <div className="capsule" style={{ paddingRight: 10 }}>
        <span id="status-dot" data-testid="status-dot" className={`status-dot ${connected ? "live" : "down"}`} />
        <span id="status-label" data-testid="status-label" className="num" style={{ fontSize: 11, color: connected ? "var(--up)" : "var(--down)" }}>
          {connected ? "LIVE · 5s" : "OFFLINE"}
        </span>
        <span id="last-update" data-testid="last-update" className="num dim" style={{ fontSize: 11 }} title={lastUpdate?.toLocaleString()}>
          {lastUpdate ? lastUpdate.toLocaleTimeString("en-IN", { hour12: false }) : "—"}
          {lastUpdate && <span className="hide-sm"> · {ago}s ago</span>}
        </span>
      </div>
    </div>
  );
};

export const ViewControls = () => {
  const { density, setDensity, audio, setAudio, setPaletteOpen } = useTerminal();
  return (
    <div className="flex items-center gap-2">
      <div className="seg" id="density-switch" data-testid="density-switch">
        <button className={density === "pro" ? "active" : ""} onClick={() => setDensity("pro")} data-testid="btn-density-pro" title="Pro Terminal (compact)">
          <Rows3 size={12} className="inline mr-1" />Pro
        </button>
        <button className={density === "analytical" ? "active" : ""} onClick={() => setDensity("analytical")} data-testid="btn-density-analytical" title="Analytical (spacious)">
          <LayoutGrid size={12} className="inline mr-1" />Analytical
        </button>
      </div>
      <button className="btn btn-xs btn-icon" id="btn-audio-toggle" data-testid="btn-audio-toggle" aria-pressed={audio}
        onClick={() => setAudio(!audio)} title={audio ? "Mute alert chime" : "Enable alert chime"}>
        {audio ? <Bell size={13} style={{ color: "var(--cyan)" }} /> : <BellOff size={13} />}
      </button>
      <button className="btn btn-xs" id="btn-command-palette" data-testid="btn-command-palette" onClick={() => setPaletteOpen(true)}>
        <Command size={12} /><span className="hide-sm">Search</span><span className="kbd">Ctrl K</span>
      </button>
    </div>
  );
};
