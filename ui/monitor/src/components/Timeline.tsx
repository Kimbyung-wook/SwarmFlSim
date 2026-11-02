// IMP-MON-020: 시퀀스 타임라인 캔버스 (src→dst 화살표, 손실 ✕, 클릭으로 echo) (REQ-UI-005, PRP-UI-002)
import { useEffect, useRef, useState } from "react";
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import type { Filter } from "../model/filter";
import { fmtSimTime } from "../model/format";
import { DROP_COLOR } from "../model/labels";
import type { MonitorStore } from "../model/store";
import type { Layout } from "../model/timeline";
import { hitArrow, laneOrder, layoutTimeline, queryTimeline, snapshotTimeline } from "../model/timeline";
import type { Ring } from "../model/ring";

const WINDOWS_S = [0.5, 1, 2, 5, 10];
const MAX_ITEMS = [200, 500, 1500];
const DELIVERED = "#4caf50";

export function Timeline(props: {
  store: MonitorStore;
  filter: Filter;
  frozen: boolean;
  picked?: LinkOutcome;
  onPick: (o: LinkOutcome | undefined) => void;
}) {
  const { store, filter, frozen, picked } = props;
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const layout = useRef<Layout | null>(null);
  const frozenEnd = useRef(0);
  const [windowS, setWindowS] = useState(2);
  const [maxItems, setMaxItems] = useState(500);
  const countEl = useRef<HTMLSpanElement>(null);

  const snap = useRef<Ring<LinkOutcome> | null>(null);
  if (!frozen) {
    frozenEnd.current = store.agg.nowUs;
    snap.current = null;
  } else if (!snap.current) {
    snap.current = snapshotTimeline(store.timeline, frozenEnd.current - WINDOWS_S[WINDOWS_S.length - 1] * 1e6);
  }
  const endUs = frozenEnd.current;
  const source = snap.current ?? store.timeline;

  useEffect(() => {
    const c = canvas.current;
    const w = wrap.current;
    if (!c || !w) return;
    const dpr = window.devicePixelRatio || 1;
    const W = w.clientWidth;
    const H = w.clientHeight;
    if (c.width !== W * dpr || c.height !== H * dpr) {
      c.width = W * dpr;
      c.height = H * dpr;
      c.style.width = `${W}px`;
      c.style.height = `${H}px`;
    }
    const g = c.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);

    const items = queryTimeline(source, { filter, endUs, windowUs: windowS * 1e6, maxItems });
    // 상한에 걸리면 표시한 항목이 걸친 구간으로 시간축을 줄인다
    let windowUs = windowS * 1e6;
    if (items.length >= maxItems) {
      const oldest = items.reduce((m, o) => Math.min(m, Number(o.txTimeUs)), endUs);
      windowUs = Math.max(10_000, endUs - oldest);
    }
    // 그린 뒤 다시 렌더하지 않도록 DOM에 직접 쓴다
    if (countEl.current) countEl.current.textContent =
        `${items.length}건` + (items.length >= maxItems ? ` (상한, 최근 ${(windowUs / 1000).toFixed(0)} ms만)` : "");
    const lanes = laneOrder(items, filter.entities);
    const box = { left: 60, right: W - 30, top: 34, bottom: H - 10 };
    const L = layoutTimeline(items, lanes, box, endUs, windowUs);
    layout.current = L;

    // 시간 눈금
    g.font = "11px ui-monospace, monospace";
    g.fillStyle = "#8a93a0";
    g.strokeStyle = "#2a2f37";
    g.lineWidth = 1;
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      const t = endUs - windowUs + (windowUs * i) / ticks;
      const y = L.y(t);
      g.beginPath();
      g.moveTo(box.left - 6, y);
      g.lineTo(box.right + 10, y);
      g.stroke();
      g.fillText(fmtSimTime(t).slice(3), 4, y + 4);
    }
    // 레인
    L.lanes.forEach((id, i) => {
      const x = L.laneX[i];
      g.strokeStyle = id.startsWith("gcs-") ? "#3d5a80" : "#39404a";
      g.beginPath();
      g.moveTo(x, box.top);
      g.lineTo(x, box.bottom);
      g.stroke();
      g.save();
      g.translate(x, box.top - 6);
      g.rotate(-Math.PI / 5);
      g.fillStyle = filter.entities.has(id) ? "#ffd166" : "#c9d1d9";
      g.fillText(id, 0, 0);
      g.restore();
    });
    // 화살표 (오래된 것부터 그려 최신이 위에 오게)
    for (let i = L.arrows.length - 1; i >= 0; i--) {
      const a = L.arrows[i];
      const sel = picked !== undefined && a.o === picked;
      const color = a.dropped ? DROP_COLOR[a.o.reason] : DELIVERED;
      g.strokeStyle = color;
      g.fillStyle = color;
      g.globalAlpha = sel ? 1 : a.dropped ? 0.9 : 0.55;
      g.lineWidth = sel ? 3 : 1;
      g.setLineDash(a.dropped ? [4, 3] : []);
      g.beginPath();
      g.moveTo(a.x1, a.y1);
      g.lineTo(a.x2, a.y2);
      g.stroke();
      g.setLineDash([]);
      if (a.dropped) {
        const s = sel ? 6 : 4;
        g.lineWidth = 2;
        g.beginPath();
        g.moveTo(a.x2 - s, a.y2 - s);
        g.lineTo(a.x2 + s, a.y2 + s);
        g.moveTo(a.x2 - s, a.y2 + s);
        g.lineTo(a.x2 + s, a.y2 - s);
        g.stroke();
      } else {
        const ang = Math.atan2(a.y2 - a.y1, a.x2 - a.x1);
        const s = sel ? 8 : 5;
        g.beginPath();
        g.moveTo(a.x2, a.y2);
        g.lineTo(a.x2 - s * Math.cos(ang - 0.4), a.y2 - s * Math.sin(ang - 0.4));
        g.lineTo(a.x2 - s * Math.cos(ang + 0.4), a.y2 - s * Math.sin(ang + 0.4));
        g.fill();
      }
    }
    g.globalAlpha = 1;
    g.lineWidth = 1;
  });

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const L = layout.current;
    if (!L) return;
    const r = e.currentTarget.getBoundingClientRect();
    props.onPick(hitArrow(L.arrows, e.clientX - r.left, e.clientY - r.top)?.o);
  };

  return (
    <div className="timeline">
      <div className="panel-title">
        시퀀스 타임라인
        <span className="tabs">
          {WINDOWS_S.map((s) => (
            <button key={s} className={windowS === s ? "on" : ""} onClick={() => setWindowS(s)}>
              {s} s
            </button>
          ))}
        </span>
        <span className="tabs">
          {MAX_ITEMS.map((n) => (
            <button key={n} className={maxItems === n ? "on" : ""} onClick={() => setMaxItems(n)} title="최신 순 최대 화살표 수">
              ≤{n}
            </button>
          ))}
        </span>
        <span className="muted small">
          <span ref={countEl} /> · 아래가 최신 · 실선 전달, 점선✕ 손실(사유별 색) · 클릭하면 echo
          {frozen ? " · 정지" : ""}
        </span>
      </div>
      <div className="canvas-wrap" ref={wrap}>
        <canvas ref={canvas} onClick={onClick} />
      </div>
    </div>
  );
}
