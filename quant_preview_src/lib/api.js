import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const REFRESH_INTERVAL = 5000;

const http = axios.create({ baseURL: API, timeout: 20000 });
export const get = (url, params) => http.get(url, { params }).then((r) => r.data);
export const post = (url, body) => http.post(url, body ?? {}).then((r) => r.data);

export const priceDp = (v) => (v == null ? 2 : Math.abs(v) < 0.01 ? 8 : Math.abs(v) < 10 ? 4 : 2);
export const fmt = (v, d = 2) =>
  v == null || Number.isNaN(Number(v))
    ? "—"
    : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
export const px = (v) => fmt(v, priceDp(v));
export const sym = (c) => (c === "USD" ? "$" : "₹");
export const money = (v, c = "INR", d = 2) => (v == null ? "—" : `${v < 0 ? "-" : ""}${sym(c)}${fmt(Math.abs(v), d)}`);
export const signedMoney = (v, c = "INR") => (v == null ? "—" : `${v > 0 ? "+" : ""}${money(v, c)}`);
export const signed = (v, d = 2) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v, d)}`);
export const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${fmt(v, 2)}%`);
export const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
export const compact = (v) =>
  v == null ? "—" : Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 2 }).format(v);
export const usd = (v) =>
  v == null ? "—" : `$${Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(v)}`;
export const timeStr = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour12: false }) : "—");
export const dateTimeStr = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })
    : "—";
export const label = (s) => (s ? s.replace(/_/g, " ") : "—");

export const INDEX_SYMBOLS = ["NIFTY50", "BANKNIFTY", "NIFTYAUTO", "MIDCPNIFTY"];
export const isCrypto = (s) => /USD$/.test(s || "");
export const BULLISH_SETUPS = ["bounce_support", "breakout_resistance", "retest_breakout", "firsty_continuation"];
