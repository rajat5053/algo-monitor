import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";
import { get, priceDp } from "@/lib/api";
import { usePoll } from "@/hooks/usePoll";

const TZ = -new Date().getTimezoneOffset() * 60;
const LEVEL_STYLE = {
  entry: { color: "#a5b4fc", title: "ENTRY", lineStyle: LineStyle.Dashed },
  stop_loss: { color: "#f43f5e", title: "SL", lineStyle: LineStyle.Dotted },
  target: { color: "#10b981", title: "TARGET", lineStyle: LineStyle.Dotted },
};

function makeChart(el) {
  const chart = createChart(el, {
    autoSize: true,
    localization: { locale: "en-IN" },
    layout: { background: { color: "transparent" }, textColor: "#94a3b8", fontFamily: "JetBrains Mono", fontSize: 11 },
    grid: { vertLines: { color: "rgba(255,255,255,0.035)" }, horzLines: { color: "rgba(255,255,255,0.035)" } },
    rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
    timeScale: { borderColor: "rgba(255,255,255,0.08)", timeVisible: true, secondsVisible: false },
    crosshair: { mode: CrosshairMode.Normal },
  });
  const series = chart.addCandlestickSeries({
    upColor: "#10b981", downColor: "#f43f5e", borderVisible: false, wickUpColor: "#10b981", wickDownColor: "#f43f5e",
  });
  const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
  return { chart, series, vol };
}

function drawZones(a, overlay) {
  if (!a.series || !overlay) return;
  overlay.style.right = `${a.chart.priceScale("right").width()}px`;
  overlay.innerHTML = (a.zones || []).map((z) => {
    const y1 = a.series.priceToCoordinate(z.price_high);
    const y2 = a.series.priceToCoordinate(z.price_low);
    if (y1 == null || y2 == null) return "";
    const top = Math.min(y1, y2);
    const h = Math.max(3, Math.abs(y2 - y1));
    const tf = (z.timeframe || z.interval || ((z.symbol && z.symbol.includes("USD")) ? "1H" : "1D")).toUpperCase();
    return `<div class="zone-band ${z.type}" style="top:${top}px;height:${h}px"><em>${tf} ${z.type.toUpperCase()} · ${z.strength}%</em></div>`;
  }).join("");
}

export const CandleChart = ({ symbol, levels, height = 380, testid = "candle-chart" }) => {
  const box = useRef(null);
  const overlay = useRef(null);
  const a = useRef({});
  const [interval, setInterval] = useState("5m");
  const [zones, setZones] = useState([]);
  const { data } = usePoll(() => get(`/candles/${encodeURIComponent(symbol)}`, { interval }), [symbol, interval], { interval: 10000 });

  useEffect(() => {
    const created = makeChart(box.current);
    a.current = { ...created, lines: [], fitted: false, zones: [] };
    const redraw = () => requestAnimationFrame(() => drawZones(a.current, overlay.current));
    created.chart.timeScale().subscribeVisibleLogicalRangeChange(redraw);
    const ro = new ResizeObserver(redraw);
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      created.chart.remove();
      a.current = {};
    };
  }, []);

  useEffect(() => {
    a.current.fitted = false;
    get("/zones", { symbol }).then((d) => setZones(d.zones)).catch(() => setZones([]));
  }, [symbol]);

  useEffect(() => {
    const { series, vol } = a.current;
    if (!series || !data?.candles?.length || data.symbol !== symbol) return;
    const d = priceDp(data.candles[data.candles.length - 1].close);
    series.applyOptions({ priceFormat: { type: "price", precision: d, minMove: 1 / 10 ** d } });
    series.setData(data.candles.map((c) => ({ time: c.time + TZ, open: c.open, high: c.high, low: c.low, close: c.close })));
    vol.setData(data.candles.map((c) => ({
      time: c.time + TZ, value: c.volume, color: c.close >= c.open ? "rgba(16,185,129,0.28)" : "rgba(244,63,94,0.28)",
    })));
    if (!a.current.fitted) {
      a.current.chart.timeScale().fitContent();
      a.current.fitted = true;
    }
    requestAnimationFrame(() => drawZones(a.current, overlay.current));
  }, [data, symbol]);

  useEffect(() => {
    const { series } = a.current;
    if (!series) return;
    a.current.lines.forEach((l) => series.removePriceLine(l));
    a.current.zones = zones;
    a.current.lines = Object.entries(levels || {}).filter(([k, v]) => LEVEL_STYLE[k] && v != null).map(([k, v]) =>
      series.createPriceLine({ price: v, lineWidth: 1, axisLabelVisible: true, ...LEVEL_STYLE[k] }));
    requestAnimationFrame(() => drawZones(a.current, overlay.current));
  }, [zones, levels]);

  return (
    <div className="chart-box" style={{ height }} data-testid={testid}>
      <div style={{ position: "absolute", top: 8, left: 12, zIndex: 10, display: "flex", gap: 4, background: "rgba(15,23,42,0.88)", padding: "3px 6px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.12)", backdropFilter: "blur(8px)" }}>
        {["5m", "15m", "1h", "4h", "1d"].map((tf) => (
          <button
            key={tf}
            onClick={() => {
              setInterval(tf);
              if (a.current) a.current.fitted = false;
            }}
            style={{
              background: interval === tf ? "#6366f1" : "transparent",
              color: interval === tf ? "#ffffff" : "#94a3b8",
              border: "none",
              borderRadius: 4,
              padding: "2px 8px",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              textTransform: "uppercase",
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            {tf}
          </button>
        ))}
      </div>
      <div ref={box} style={{ position: "absolute", inset: 0 }} />
      <div ref={overlay} className="zone-overlay" style={{ bottom: 28 }} data-testid={`${testid}-zones`} />
    </div>
  );
};
