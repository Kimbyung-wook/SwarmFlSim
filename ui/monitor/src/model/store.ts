// IMP-MON-009: 모니터 상태 보관소. 프레임 해석 → 집계·타임라인·echo·엔티티 목록 (REQ-UI-005, PRP-UI-002)
// React와 분리한다. 프레임마다 동기 처리하고, 화면은 주기적으로 읽는다.
import type { BusFrame } from "../bridge/frame";
import type { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import { EntityKind as EK, Side as SD } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope, LinkOutcome, LinkState } from "../gen/swarm/v1/link_pb";
import type { L1Interface } from "../gen/swarm/v1/options_pb";
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import { Aggregator } from "./aggregator";
import type { BusEvent, Direction } from "./decode";
import { decodeBusFrame } from "./decode";
import { FrameGapCounter, peekFrameNumber, waitingWarning } from "./frameGap";
import { IFACE_KEY, shortType } from "./labels";
import { Ring } from "./ring";

export interface EntityInfo {
  id: string;
  kind: EntityKind;
  side: Side;
  alive: boolean;
  /** truth/state에서 확인한 엔티티인가 (아니면 트래픽에서만 본 것) */
  fromTruth: boolean;
}

export interface EnvelopeRecord {
  dir: Direction;
  /** tx: 송신 엔티티, rx: 수신 엔티티 (키의 <id>) */
  entity: string;
  key: string;
  src: string;
  seq: number;
  iface: L1Interface;
  msgType: string;
  /** tx: header.sim_time_us, rx: rx_time_us */
  tUs: number;
  bytes: number;
  env: LinkEnvelope;
}

export type RunView = "live" | "replay";
/** 재생 표시를 정한 근거. status: SimStatus.replay(DEC-031), query: `?replay=1` 대체, manual: 배지 전환 */
export type ViewSource = "status" | "query" | "manual";

export interface StoreOptions {
  timelineCapacity?: number;
  echoCapacity?: number;
  /** outcome → 송신 엔벨로프 찾기용 tx 보관 수. tx는 rx보다 훨씬 적으므로 따로 길게 둔다 */
  txCapacity?: number;
  /** 시각이 이만큼 거꾸로 가면 재생 되감기로 보고 집계를 지운다 */
  rewindUs?: number;
  /** 성능 측정(performance.now)을 끈다. 부하 측정 기준선용 */
  noTiming?: boolean;
  /** truth/state 해석 최소 간격(ms, 벽시계). 프레임 번호는 매번 읽는다. 기본 1000 */
  truthDecodeMs?: number;
}

export function txKeyOf(o: LinkOutcome): string {
  return `swarm/${o.src}/tx/${IFACE_KEY[o.iface]}/${shortType(o.msgType)}`;
}

const now = (): number => (typeof performance !== "undefined" ? performance.now() : Date.now());

export class MonitorStore {
  readonly agg = new Aggregator();
  readonly timeline: Ring<LinkOutcome>;
  readonly echo: Ring<EnvelopeRecord>;
  private readonly txRing: Ring<EnvelopeRecord>;
  readonly entities = new Map<string, EntityInfo>();
  readonly linkStates = new Map<string, LinkState>();
  readonly msgTypes = new Set<string>();
  /** tx 엔벨로프 색인: `${key}#${seq}` */
  private readonly txIndex = new Map<string, EnvelopeRecord>();
  status: SimStatus | undefined;
  /** SimStatus가 없을 때 쓰는 재생 표시(`?replay=1`) */
  viewHint: RunView = "live";
  /** 배지로 바꾼 표시. SimStatus.replay 값이 바뀌면 지운다 */
  private viewManual: RunView | undefined;
  rewinds = 0;
  readonly gaps = new FrameGapCounter();
  private readonly truthDecodeMs: number;
  private lastTruthDecodeMs = Number.NEGATIVE_INFINITY;
  /** 시계 출처(sim/ctrl/status, truth/state)의 최신 시각(µs). 되감기 판정 기준 */
  clockUs = 0;
  /** 가장 최근 outcome을 받은 순간의 (시계 − outcome tx 시각)(µs)와 그때의 시계 */
  private lagSampleUs = 0;
  private lagAtUs = 0;
  /** 처리한 프레임 수, 해석 실패·무시 수, 누적 처리 시간(ms) */
  frames = 0;
  ignored = 0;
  lastIgnored = "";
  busyMs = 0;
  /** 화면 갱신 판단용. 상태가 바뀔 때마다 증가한다 */
  version = 0;
  private readonly rewindUs: number;
  private readonly staleUs = 5_000_000;
  private readonly timing: boolean;

  constructor(opts: StoreOptions = {}) {
    this.timeline = new Ring(opts.timelineCapacity ?? 20_000);
    this.echo = new Ring(opts.echoCapacity ?? 5_000);
    this.txRing = new Ring(opts.txCapacity ?? 20_000);
    this.rewindUs = opts.rewindUs ?? 5_000_000;
    this.timing = !opts.noTiming;
    this.truthDecodeMs = opts.truthDecodeMs ?? 1000;
  }

  handleFrame(f: BusFrame): void {
    const t0 = this.timing ? now() : 0;
    this.frames++;
    if (f.key === "truth/state") {
      const n = peekFrameNumber(f.payload);
      if (n !== null) this.gaps.feed(n, this.status?.replay === true);
      // 엔티티 목록은 느리게 변하므로 해석은 truthDecodeMs마다 한 번만 한다
      const t = Date.now();
      if (t - this.lastTruthDecodeMs < this.truthDecodeMs) {
        this.version++;
        if (this.timing) this.busyMs += now() - t0;
        return;
      }
      this.lastTruthDecodeMs = t;
    }
    this.handleEvent(decodeBusFrame(f));
    if (this.timing) this.busyMs += now() - t0;
  }

  /** DEC-042: 재생 중 빠진 truth/state 프레임 수 */
  get missedFrames(): number {
    return this.status?.replay === true ? this.gaps.missed : 0;
  }

  /** DEC-041: 응답 없는 참여자 경고 문구. 없으면 null */
  get waitingWarning(): string | null {
    return waitingWarning(this.status?.waitingParticipants);
  }

  handleEvent(ev: BusEvent): void {
    this.version++;
    switch (ev.kind) {
      case "outcome":
        return this.onOutcome(ev.outcome);
      case "envelope":
        return this.onEnvelope(ev.dir, ev.entity, ev.key, ev.env);
      case "linkState": {
        const s = ev.state;
        this.linkStates.set(`${s.a}|${s.b}`, s);
        this.seen(s.a);
        this.seen(s.b);
        return;
      }
      case "truth":
        for (const e of ev.frame.entities) {
          const cur = this.entities.get(e.id);
          if (cur && cur.fromTruth && cur.kind === e.kind && cur.side === e.side && cur.alive === e.alive) continue;
          this.entities.set(e.id, { id: e.id, kind: e.kind, side: e.side, alive: e.alive, fromTruth: true });
        }
        if (ev.frame.header) this.onClock(Number(ev.frame.header.simTimeUs));
        return;
      case "truthEvent": {
        const e = ev.event.event;
        if (e.case === "spawn" && e.value.entity) {
          const s = e.value.entity;
          this.entities.set(s.id, { id: s.id, kind: s.kind, side: s.side, alive: true, fromTruth: true });
        } else if (e.case === "kill") {
          const cur = this.entities.get(e.value.entityId);
          if (cur) cur.alive = false;
        }
        return;
      }
      case "status":
        if (this.status && this.status.replay !== ev.status.replay) this.viewManual = undefined;
        this.status = ev.status;
        this.onClock(Number(ev.status.simTimeUs));
        this.agg.advance(Number(ev.status.simTimeUs));
        return;
      case "ignored":
        this.ignored++;
        this.lastIgnored = `${ev.key}: ${ev.reason}`;
        return;
    }
  }

  private onOutcome(o: LinkOutcome): void {
    const t = Number(o.txTimeUs);
    if (this.clockUs > 0 && t > 0) {
      this.lagSampleUs = Math.max(0, this.clockUs - t);
      this.lagAtUs = this.clockUs;
    }
    this.agg.addOutcome(o);
    this.timeline.push(o);
    this.msgTypes.add(o.msgType);
    this.seen(o.src);
    this.seen(o.dst);
  }

  private onEnvelope(dir: Direction, entity: string, key: string, env: LinkEnvelope): void {
    const src = env.header?.source || (dir === "tx" ? entity : "");
    const tUs = dir === "tx" ? Number(env.header?.simTimeUs ?? 0n) : Number(env.rxTimeUs);
    const rec: EnvelopeRecord = {
      dir,
      entity,
      key,
      src,
      seq: env.header?.seq ?? 0,
      iface: env.iface,
      msgType: env.msgType,
      tUs,
      bytes: env.payload.length,
      env,
    };
    this.agg.addEnvelope(dir, entity, tUs, rec.bytes);
    this.msgTypes.add(env.msgType);
    this.seen(entity);
    if (src) this.seen(src);
    this.echo.push(rec);
    if (dir === "tx") {
      const old = this.txRing.push(rec);
      if (old) {
        const k = `${old.key}#${old.seq}`;
        if (this.txIndex.get(k) === old) this.txIndex.delete(k);
      }
      this.txIndex.set(`${key}#${rec.seq}`, rec);
    }
  }

  /** outcome에 대응하는 송신 엔벨로프 (tx 보관분에 남아 있을 때) */
  envelopeFor(o: LinkOutcome): EnvelopeRecord | undefined {
    return this.txIndex.get(`${txKeyOf(o)}#${o.seq}`);
  }

  private seen(id: string): void {
    if (!id || this.entities.has(id)) return;
    this.entities.set(id, { id, kind: EK.UNSPECIFIED, side: SD.UNSPECIFIED, alive: true, fromTruth: false });
  }

  /** 재생 표시는 SimStatus.replay로 판단한다(DEC-031). SimStatus를 받기 전에만 `?replay=1`을 쓴다 */
  get viewSource(): ViewSource {
    if (this.viewManual) return "manual";
    return this.status ? "status" : "query";
  }

  get view(): RunView {
    if (this.viewManual) return this.viewManual;
    if (this.status) return this.status.replay ? "replay" : "live";
    return this.viewHint;
  }

  toggleView(): void {
    this.viewManual = this.view === "live" ? "replay" : "live";
    this.version++;
  }

  /**
   * 데이터링크가 시계보다 늦은 정도(µs). outcome을 받은 순간의 (sim 시계 − outcome tx 시각)이다.
   * 둘 다 sim 시각이라 재생 배속과 무관하다. 트래픽이 없는 구간을 지연으로 보지 않도록,
   * 마지막 outcome 이후 sim 시계가 staleUs 넘게 흐르면 0으로 본다.
   */
  get linkLagUs(): number {
    return this.lagSampleUs > 0 && this.clockUs - this.lagAtUs <= this.staleUs ? this.lagSampleUs : 0;
  }

  /** 되감기는 시계 출처로만 판정한다. outcome·엔벨로프는 데이터링크가 밀리면 늦게 오므로 쓰지 않는다 */
  private onClock(tUs: number): void {
    if (this.clockUs > 0 && tUs > 0 && tUs + this.rewindUs < this.clockUs) {
      this.rewinds++;
      this.clearStats();
      this.lagSampleUs = 0;
      this.lagAtUs = 0;
      this.clockUs = tUs;
      return;
    }
    if (tUs > this.clockUs) this.clockUs = tUs;
  }

  /** 집계·타임라인·echo를 지운다. 엔티티 목록과 링크 상태는 둔다 */
  clearStats(): void {
    this.agg.clear();
    this.timeline.clear();
    this.echo.clear();
    this.txRing.clear();
    this.txIndex.clear();
    this.version++;
  }
}
