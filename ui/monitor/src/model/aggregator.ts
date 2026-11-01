// IMP-MON-006: 엔티티별 송수신 집계 (빈도·크기·지연·손실률, 손실 사유별) (REQ-UI-005, PRP-UI-002, PRP-LNK-002)
// LinkOutcome 한 건당 O(1). 빈도는 시뮬레이션 시각 기준 이동 창으로 계산해 재생 배속과 무관하다.
import type { LinkOutcome } from "../gen/swarm/v1/link_pb";
import { LinkOutcomeKind } from "../gen/swarm/v1/link_pb";
import type { L1Interface } from "../gen/swarm/v1/options_pb";
import { REASON_SLOTS, reasonSlot } from "./labels";

export const BUCKET_US = 500_000;
export const WINDOW_BUCKETS = 10; // 5 s 창

/** 시각 버킷 원형 버퍼. 버킷마다 [건수, 바이트, 손실] */
export class RateWindow {
  private readonly ids = new Float64Array(WINDOW_BUCKETS + 1).fill(-1);
  private readonly cnt = new Float64Array(WINDOW_BUCKETS + 1);
  private readonly bytes = new Float64Array(WINDOW_BUCKETS + 1);
  private readonly drop = new Float64Array(WINDOW_BUCKETS + 1);

  add(tUs: number, bytes: number, dropped: boolean): void {
    const id = Math.floor(tUs / BUCKET_US);
    const i = id % this.ids.length;
    if (this.ids[i] !== id) {
      // 오래된 버킷이면 무시(늦게 도착한 outcome이 창 밖)
      if (this.ids[i] > id) return;
      this.ids[i] = id;
      this.cnt[i] = 0;
      this.bytes[i] = 0;
      this.drop[i] = 0;
    }
    this.cnt[i]++;
    this.bytes[i] += bytes;
    if (dropped) this.drop[i]++;
  }

  /** nowUs 직전까지 완료된 WINDOW_BUCKETS개 버킷 합의 초당 값 */
  rates(nowUs: number): { perS: number; bytesPerS: number; dropPerS: number } {
    const cur = Math.floor(nowUs / BUCKET_US);
    let c = 0;
    let b = 0;
    let d = 0;
    for (let i = 0; i < this.ids.length; i++) {
      const id = this.ids[i];
      if (id >= cur - WINDOW_BUCKETS && id < cur) {
        c += this.cnt[i];
        b += this.bytes[i];
        d += this.drop[i];
      }
    }
    const s = (WINDOW_BUCKETS * BUCKET_US) / 1e6;
    return { perS: c / s, bytesPerS: b / s, dropPerS: d / s };
  }
}

/** 지연 히스토그램: 1 µs ~ 약 67 s, 2^(1/4) 간격 */
export const LAT_BINS = 104;
export function latencyBin(us: number): number {
  if (us < 1) return 0;
  return Math.min(LAT_BINS - 1, Math.floor(Math.log2(us) * 4) + 1);
}
export function binUpperUs(bin: number): number {
  return bin === 0 ? 1 : Math.pow(2, bin / 4);
}

export class DirStats {
  /** outcome 건수 (수신자 한 명당 하나) */
  total = 0;
  delivered = 0;
  dropped = 0;
  bytes = 0;
  readonly drops = new Uint32Array(REASON_SLOTS);
  latSumUs = 0;
  latMaxUs = 0;
  readonly latHist = new Uint32Array(LAT_BINS);
  readonly window = new RateWindow();

  add(o: LinkOutcome, txUs: number): void {
    this.total++;
    this.bytes += o.sizeBytes;
    const dropped = o.outcome === LinkOutcomeKind.DROPPED;
    if (dropped) {
      this.dropped++;
      this.drops[reasonSlot(o.reason)]++;
    } else if (o.outcome === LinkOutcomeKind.DELIVERED) {
      this.delivered++;
      const lat = Math.max(0, Number(o.rxTimeUs) - txUs);
      this.latSumUs += lat;
      if (lat > this.latMaxUs) this.latMaxUs = lat;
      this.latHist[latencyBin(lat)]++;
    }
    this.window.add(txUs, o.sizeBytes, dropped);
  }

  lossRate(): number {
    const n = this.delivered + this.dropped;
    return n === 0 ? 0 : this.dropped / n;
  }

  latMeanUs(): number {
    return this.delivered === 0 ? 0 : this.latSumUs / this.delivered;
  }

  /** 히스토그램 버킷 상한으로 근사한 분위수 */
  latQuantileUs(q: number): number {
    if (this.delivered === 0) return 0;
    const target = q * this.delivered;
    let acc = 0;
    for (let i = 0; i < LAT_BINS; i++) {
      acc += this.latHist[i];
      if (acc >= target) return Math.min(binUpperUs(i), this.latMaxUs);
    }
    return this.latMaxUs;
  }
}

export interface TypeStats {
  msgType: string;
  iface: L1Interface;
  total: number;
  dropped: number;
  bytes: number;
}

export class EntityStats {
  readonly tx = new DirStats();
  readonly rx = new DirStats();
  /** 송신 엔벨로프 수(브로드캐스트 1건 = 1). swarm/<id>/tx/** */
  envTx = 0;
  /** 수신 엔벨로프 수. swarm/<id>/rx/** */
  envRx = 0;
  readonly envTxWin = new RateWindow();
  readonly envRxWin = new RateWindow();
  /** 송신 기준 메시지 타입별 */
  readonly txTypes = new Map<string, TypeStats>();
  readonly rxTypes = new Map<string, TypeStats>();
  lastUs = 0;

  constructor(readonly id: string) {}
}

export interface PairStats {
  src: string;
  dst: string;
  total: number;
  dropped: number;
  lastReason: number;
  lastUs: number;
}

function bumpType(m: Map<string, TypeStats>, o: LinkOutcome, dropped: boolean): void {
  let t = m.get(o.msgType);
  if (!t) {
    t = { msgType: o.msgType, iface: o.iface, total: 0, dropped: 0, bytes: 0 };
    m.set(o.msgType, t);
  }
  t.total++;
  t.bytes += o.sizeBytes;
  if (dropped) t.dropped++;
}

export class Aggregator {
  readonly entities = new Map<string, EntityStats>();
  readonly pairs = new Map<string, PairStats>();
  all = new DirStats();
  /** 지금까지 본 가장 늦은 시뮬레이션 시각(µs) */
  nowUs = 0;
  outcomes = 0;

  entity(id: string): EntityStats {
    let e = this.entities.get(id);
    if (!e) {
      e = new EntityStats(id);
      this.entities.set(id, e);
    }
    return e;
  }

  addOutcome(o: LinkOutcome): void {
    const t = Number(o.txTimeUs);
    if (t > this.nowUs) this.nowUs = t;
    this.outcomes++;
    const dropped = o.outcome === LinkOutcomeKind.DROPPED;
    const s = this.entity(o.src);
    const d = this.entity(o.dst);
    s.tx.add(o, t);
    d.rx.add(o, t);
    s.lastUs = d.lastUs = t;
    bumpType(s.txTypes, o, dropped);
    bumpType(d.rxTypes, o, dropped);
    this.all.add(o, t);

    const pk = `${o.src}>${o.dst}`;
    let p = this.pairs.get(pk);
    if (!p) {
      p = { src: o.src, dst: o.dst, total: 0, dropped: 0, lastReason: 0, lastUs: 0 };
      this.pairs.set(pk, p);
    }
    p.total++;
    p.lastUs = t;
    if (dropped) {
      p.dropped++;
      p.lastReason = o.reason;
    }
  }

  addEnvelope(dir: "tx" | "rx", entity: string, tUs: number, bytes: number): void {
    if (tUs > this.nowUs) this.nowUs = tUs;
    const e = this.entity(entity);
    if (dir === "tx") {
      e.envTx++;
      e.envTxWin.add(tUs, bytes, false);
    } else {
      e.envRx++;
      e.envRxWin.add(tUs, bytes, false);
    }
  }

  /** 시뮬레이션 시각을 outcome 없이도 진행한다 (SimStatus) */
  advance(tUs: number): void {
    if (tUs > this.nowUs) this.nowUs = tUs;
  }

  clear(): void {
    this.entities.clear();
    this.pairs.clear();
    this.all = new DirStats();
    this.nowUs = 0;
    this.outcomes = 0;
  }
}
