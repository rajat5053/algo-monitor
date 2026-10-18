let ctx;

export function chime(kind = "signal") {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    const notes = kind === "loss" ? [523, 392] : [880, 1318];
    notes.forEach((f, i) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      const t = ctx.currentTime + i * 0.11;
      o.type = "sine";
      o.frequency.value = f;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.07, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.38);
      o.connect(g).connect(ctx.destination);
      o.start(t);
      o.stop(t + 0.42);
    });
  } catch (e) {
    /* audio unavailable */
  }
}
