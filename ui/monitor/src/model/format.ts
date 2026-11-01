// IMP-MON-013: 표시 형식 (REQ-UI-005)
export function fmtRate(v: number): string {
  if (v === 0) return "0";
  if (v < 10) return v.toFixed(1);
  return Math.round(v).toLocaleString("en-US");
}

export function fmtBytes(v: number): string {
  if (v < 1024) return `${Math.round(v)} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${(v / 1024 / 1024).toFixed(2)} MiB`;
}

export function fmtMs(us: number): string {
  if (us === 0) return "–";
  const ms = us / 1000;
  return ms < 10 ? ms.toFixed(2) : ms < 100 ? ms.toFixed(1) : Math.round(ms).toString();
}

export function fmtPct(r: number): string {
  if (r === 0) return "0%";
  return r < 0.001 ? "<0.1%" : `${(r * 100).toFixed(1)}%`;
}

/** 시뮬레이션 시각 µs → mm:ss.mmm */
export function fmtSimTime(us: number | bigint): string {
  const t = Number(us) / 1e6;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(3).padStart(6, "0")}`;
}

/** JSON.stringify가 bigint를 못 다루므로 문자열로 바꾼다 */
export function stringifyJson(v: unknown): string {
  return JSON.stringify(v, (_k, x) => (typeof x === "bigint" ? x.toString() : x), 2);
}
