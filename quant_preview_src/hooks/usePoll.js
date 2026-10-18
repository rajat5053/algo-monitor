import { useEffect, useRef, useState, useCallback } from "react";
import { REFRESH_INTERVAL } from "@/lib/api";

export function usePoll(fn, deps = [], { interval = REFRESH_INTERVAL, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const fnRef = useRef(fn);
  const seq = useRef(0);
  fnRef.current = fn;

  const run = useCallback(async (token) => {
    try {
      const d = await fnRef.current();
      if (token !== undefined && token !== seq.current) return;
      setData(d);
      setError(null);
      window.dispatchEvent(new Event("am:data"));
    } catch (e) {
      setError(e);
      window.dispatchEvent(new Event("am:error"));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    const token = ++seq.current;
    run(token);
    const id = setInterval(() => run(token), interval);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, interval, run, ...deps]);

  return { data, error, loading: data === null && !error, refresh: () => run(seq.current) };
}

export function useFlash(value) {
  const prev = useRef(value);
  const [cls, setCls] = useState("");
  useEffect(() => {
    const p = prev.current;
    prev.current = value;
    if (p == null || value == null || value === p) {
      return undefined;
    }
    setCls(value > p ? "flash-up" : "flash-down");
    const t = setTimeout(() => setCls(""), 650);
    return () => clearTimeout(t);
  }, [value]);
  return cls;
}

export function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}
