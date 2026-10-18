import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { get, post, REFRESH_INTERVAL } from "@/lib/api";
import { chime } from "@/lib/chime";

const Ctx = createContext(null);
export const useTerminal = () => useContext(Ctx);
const stored = (k, d) => localStorage.getItem(k) ?? d;

function useCatalog() {
  const [catalog, setCatalog] = useState({ indices: [], stocks: [], crypto: [] });
  useEffect(() => {
    Promise.all([get("/indian/indices"), get("/indian/fno-securities"), get("/crypto/market")])
      .then(([i, f, c]) =>
        setCatalog({
          indices: i.items.map((x) => ({ symbol: x.symbol, name: x.name })),
          stocks: f.items.map((x) => ({ symbol: x.symbol, name: x.name })),
          crypto: c.perpetuals.map((x) => ({ symbol: x.symbol, name: x.contract })),
        }),
      )
      .catch(() => {});
  }, []);
  return catalog;
}

const levelKind = (l) => (l === "danger" ? "error" : l === "success" ? "success" : "info");

export function TerminalProvider({ children }) {
  const [tab, setTab] = useState("overview");
  const [toggles, setToggles] = useState({ indian: true, crypto: true });
  const [auth, setAuth] = useState(null);
  const [status, setStatus] = useState(null);
  const [connected, setConnected] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [density, setDensity] = useState(() => stored("am-density", "analytical"));
  const [audio, setAudio] = useState(() => stored("am-audio", "on") === "on");
  const [refreshing, setRefreshing] = useState(false);
  const [chainSymbol, setChainSymbol] = useState("NIFTY50");
  const [chartSymbol, setChartSymbol] = useState("NIFTY50");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const catalog = useCatalog();
  const audioRef = useRef(audio);
  const seen = useRef(null);
  audioRef.current = audio;

  useEffect(() => {
    localStorage.setItem("am-density", density);
    document.documentElement.dataset.density = density;
  }, [density]);
  useEffect(() => {
    localStorage.setItem("am-audio", audio ? "on" : "off");
  }, [audio]);

  const notify = useCallback((title, description, kind = "info", sound = true) => {
    const fn = { success: toast.success, error: toast.error, warning: toast.warning }[kind] || toast.info;
    fn(title, { description });
    if (sound && audioRef.current) chime(kind === "error" ? "loss" : "signal");
  }, []);

  useEffect(() => {
    const ok = () => {
      setConnected(true);
      setLastUpdate(new Date());
    };
    const bad = () => setConnected(false);
    window.addEventListener("am:data", ok);
    window.addEventListener("am:error", bad);
    return () => {
      window.removeEventListener("am:data", ok);
      window.removeEventListener("am:error", bad);
    };
  }, []);

  const pollGlobal = useCallback(async () => {
    try {
      const [s, t, a, al] = await Promise.all([
        get("/status"), get("/market-toggle"), get("/upstox/auth-status"), get("/alerts"),
      ]);
      setStatus(s);
      setToggles(t);
      setAuth(a);
      setConnected(true);
      setLastUpdate(new Date());
      if (seen.current === null) {
        seen.current = new Set(al.alerts.map((x) => x.id));
        return;
      }
      al.alerts.filter((x) => !seen.current.has(x.id)).reverse().forEach((x) => {
        seen.current.add(x.id);
        notify(x.title, x.message, levelKind(x.level));
      });
    } catch (e) {
      setConnected(false);
    }
  }, [notify]);

  useEffect(() => {
    pollGlobal();
    const id = setInterval(pollGlobal, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [pollGlobal]);

  const setMarket = useCallback(async (market, value) => {
    setToggles((t) => ({ ...t, [market]: value }));
    const name = market === "indian" ? "Indian" : "Crypto";
    try {
      setToggles(await post("/market-toggle", { [market]: value }));
      notify(`${name} market ${value ? "enabled" : "disabled"}`, value ? "Feed polling resumed" : "Feed paused", value ? "success" : "warning", false);
    } catch (e) {
      setToggles((t) => ({ ...t, [market]: !value }));
      notify("Toggle failed", "Could not reach /api/market-toggle", "error");
    }
  }, [notify]);

  const refreshToken = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await post("/upstox/refresh-token");
      setAuth(r);
      notify("Upstox Token Refreshed", r.message, "success");
    } catch (e) {
      notify("Upstox token refresh failed", "Check UPSTOX credentials in .env", "error");
    } finally {
      setRefreshing(false);
    }
  }, [notify]);

  const openChain = useCallback((s) => {
    setChainSymbol(s);
    setTab("optionchain");
    window.scrollTo({ top: 0 });
  }, []);
  const openChart = useCallback((s) => {
    setChartSymbol(s);
    setTab("overview");
    setTimeout(() => document.getElementById("chart-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
  }, []);

  const value = {
    tab, setTab, toggles, setMarket, auth, status, connected, lastUpdate, density, setDensity, audio, setAudio,
    refreshing, refreshToken, chainSymbol, setChainSymbol, chartSymbol, setChartSymbol, openChain, openChart,
    paletteOpen, setPaletteOpen, catalog, notify,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
