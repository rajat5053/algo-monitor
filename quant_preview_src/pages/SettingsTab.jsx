import { useTerminal } from "@/context/TerminalContext";
import { usePoll } from "@/hooks/usePoll";
import { dateTimeStr, fmt, get, money } from "@/lib/api";
import { Badge, Panel, SectionTitle, Stat } from "@/components/terminal/Primitives";
import { RiskGauge } from "@/components/terminal/RiskGauge";
import { AlertTriangle, Keyboard, KeyRound, RefreshCw, ShieldCheck, Sliders } from "lucide-react";

const onOff = (v) => <Badge tone={v ? "up" : "down"}>{v ? "Enabled" : "Disabled"}</Badge>;

const UpstoxCard = () => {
  const { auth, refreshToken, refreshing } = useTerminal();
  return (
    <Panel id="settings-upstox-card" title="Upstox 2FA & Access Token" icon={KeyRound} sub="TOTP-based auto-login using credentials in backend .env">
      <Stat k="Auto-login configured (.env)" v={auth ? onOff(auth.auto_login_configured) : "—"} testid="cfg-upstox-autologin" />
      <Stat k="Token status" v={auth ? <Badge tone={auth.valid ? "up" : "amber"}>{auth.status}</Badge> : "—"} testid="cfg-upstox-status" />
      <Stat k="Last token updated" v={dateTimeStr(auth?.last_updated)} testid="cfg-upstox-last-updated" />
      <Stat k="Expires at" v={dateTimeStr(auth?.expires_at)} testid="cfg-upstox-expires" />
      {auth?.error && (
        <div className="banner banner-danger mt-3 text-xs" id="upstox-auth-error" data-testid="upstox-auth-error"><AlertTriangle size={14} />{auth.error}</div>
      )}
      <button className="btn btn-primary w-full mt-4" onClick={refreshToken} disabled={refreshing} id="btn-settings-refresh-token" data-testid="btn-settings-refresh-token">
        <RefreshCw size={13} className={refreshing ? "spin" : ""} />{refreshing ? "Generating token…" : "Generate & Refresh Upstox Token"}
      </button>
    </Panel>
  );
};

const OptionsCard = ({ o }) => (
  <Panel id="settings-options-card" title="Options Trading Engine" icon={Sliders}>
    <Stat k="Options module" v={onOff(o.enabled)} testid="cfg-options-enabled" />
    <Stat k="Auto-route indices to options" v={onOff(o.auto_route_indices)} testid="cfg-auto-route" />
    <Stat k="Max capital per trade" v={`${fmt(o.max_capital_per_trade_pct, 1)}%`} testid="cfg-max-capital-pct" />
    <Stat k="Max stop-loss on premium" v={`${fmt(o.max_sl_pct_premium, 1)}%`} testid="cfg-max-sl-premium" />
    <Stat k={`Greeks model (${o.greeks_model})`} v={onOff(o.greeks_enabled)} testid="cfg-greeks-model" />
    <Stat k="Weekly expiry cycle" v={o.weekly_expiry} testid="cfg-weekly-expiry" />
  </Panel>
);

const RiskCard = ({ c }) => (
  <Panel id="settings-risk-card" title="Quant Capital & Risk Rules" icon={ShieldCheck}>
    <Stat k="Starting capital" v={money(c.starting_balance, "INR", 0)} testid="cfg-starting-balance" />
    <Stat k="Broker leverage cap" v={`${fmt(c.leverage_cap, 1)}x`} testid="cfg-leverage" />
    <Stat k="Risk per trade" v={`${fmt(c.risk_per_trade_pct, 1)}%`} testid="cfg-risk-per-trade" />
    <Stat k="Max simultaneous positions" v={c.max_positions} testid="cfg-max-positions" />
    <Stat k="Daily loss circuit breaker" v={`${fmt(c.daily_loss_limit_pct, 1)}% / ${money(c.daily_loss_limit, "INR", 0)}`} testid="cfg-daily-loss" />
    <Stat k="Trading mode" v={<Badge tone="cyan">{c.trading_mode === "PAPER" ? "Paper Simulation" : c.trading_mode}</Badge>} testid="cfg-trading-mode" />
  </Panel>
);

const SHORTCUTS = [["Ctrl/⌘ + K  or  /", "Open command palette"], ["Alt + 1…7", "Switch tabs"], ["Alt + I", "Toggle Indian market"], ["Alt + C", "Toggle Crypto market"], ["Alt + R", "Refresh Upstox token"]];

const Prefs = () => {
  const { density, setDensity, audio, setAudio } = useTerminal();
  return (
    <Panel id="settings-preferences" title="Terminal Preferences & Shortcuts" icon={Keyboard}>
      <Stat k="Viewport density" v={<div className="seg"><button className={density === "pro" ? "active" : ""} onClick={() => setDensity("pro")} data-testid="settings-density-pro">Pro Terminal</button><button className={density === "analytical" ? "active" : ""} onClick={() => setDensity("analytical")} data-testid="settings-density-analytical">Analytical</button></div>} />
      <Stat k="Audio alert chime" v={<button role="switch" aria-checked={audio} className="am-switch indigo" onClick={() => setAudio(!audio)} data-testid="settings-audio-switch" />} />
      {SHORTCUTS.map(([k, v]) => <Stat key={k} k={v} v={<span className="kbd">{k}</span>} />)}
    </Panel>
  );
};

export default function SettingsTab() {
  const { data: cfg } = usePoll(() => get("/config"), [], { interval: 30000 });
  const { data: bal } = usePoll(() => get("/balance"), []);
  return (
    <div className="am-stack">
      <SectionTitle title="⚙️ Settings & Risk Rules" sub="Broker auth, options engine and capital protection (read-only, from backend config)" />
      <div className="am-grid">
        <div className="col-span-12 lg:col-span-6 2xl:col-span-4"><UpstoxCard /></div>
        <div className="col-span-12 lg:col-span-6 2xl:col-span-4">{cfg ? <OptionsCard o={cfg.options} /> : <div className="skel h-72" />}</div>
        <div className="col-span-12 lg:col-span-6 2xl:col-span-4">{cfg ? <RiskCard c={cfg} /> : <div className="skel h-72" />}</div>
        <div className="col-span-12 lg:col-span-6 2xl:col-span-6"><RiskGauge balance={bal} id="risk-gauge-settings" /></div>
        <div className="col-span-12 2xl:col-span-6"><Prefs /></div>
      </div>
    </div>
  );
}
