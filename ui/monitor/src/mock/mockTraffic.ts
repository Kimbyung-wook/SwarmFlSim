// IMP-MON-011: 목 트래픽 생성기. 브리지 프로토콜 v1과 같은 BusFrame을 만든다 (REQ-UI-005, PRP-LNK-001, PRP-LNK-002)
// 브리지(WP5)·데이터링크(WP4)가 없을 때 모니터를 개발·시험하기 위한 것이다. 링크 모델은 손실 사유가 골고루
// 나오도록 단순화했다(거리, 가시선 차단 구역, 재밍 영역, Gilbert-Elliott 버스트, 토큰 버킷 큐, 고장 주입, 노드 파괴).
// 시드가 같으면 같은 프레임열을 만든다.
import type { DescMessage, MessageInitShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { BusFrame } from "../bridge/frame";
import { decodeFrame, encodeFrame, PROTOBUF_ENCODING_PREFIX } from "../bridge/frame";
import { CommandState } from "../gen/swarm/v1/common_pb";
import { TaskCommandSchema, TaskStatusSchema } from "../gen/swarm/v1/c2_pb";
import { EntityKind, Side } from "../gen/swarm/v1/entity_pb";
import {
  DropReason,
  LinkEnvelopeSchema,
  LinkOutcomeKind,
  LinkOutcomeSchema,
  LinkStateKind,
  LinkStateSchema,
} from "../gen/swarm/v1/link_pb";
import { RoutePlanSchema } from "../gen/swarm/v1/mp_pb";
import { SensorActivitySchema } from "../gen/swarm/v1/ms_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import { PeerStatusSchema, TrackShareSchema } from "../gen/swarm/v1/p2p_pb";
import { RunMode, SimRunState, SimStatusSchema } from "../gen/swarm/v1/sim_pb";
import { TruthEventSchema, TruthFrameSchema } from "../gen/swarm/v1/truth_pb";
import { IFACE_KEY, shortType } from "../model/labels";

export interface MockOptions {
  uavs?: number;
  /** UAV 한 대의 PeerStatus 브로드캐스트 주기(Hz) */
  peerHz?: number;
  frameHz?: number;
  seed?: number;
  /** 프레임을 Uint8Array로 직렬화했다가 다시 푼다(실제 브리지와 같은 경로) */
  wire?: boolean;
  /** MCAP 재생기처럼 SimStatus.replay=true로 낸다 (DEC-031) */
  replay?: boolean;
}

const ORIGIN = { lat: 37.5, lon: 127.0 };
const M_PER_DEG = 111_320;
const C_MPS = 299_792_458;

export const MOCK_GCS = "gcs-01";
export const MOCK_JAM_SITE = "site-01";
/** 30–40 s(120 s 주기) 모든 링크 차단 */
export const MOCK_FAULT_UAV = "uav-007";
export const MOCK_FAULT_WINDOW_S: [number, number] = [30, 40];
/** 90 s에 파괴 */
export const MOCK_DEAD_UAV_INDEX = 19;
export const MOCK_DEAD_AT_S = 90;
const JAM = { e: 6000, n: 1500, r: 2500, onS: 10, offS: 50, periodS: 60 };
/** GCS 기준 방위 200–230°, 6 km 너머는 능선으로 가시선 차단 */
const RIDGE = { fromDeg: 200, toDeg: 230, minM: 6000 };
const RANGE_P2P_M = 14000;
const RANGE_GCS_M = 18000;
/** 송신 엔티티별 토큰 버킷(바이트/s, 버스트) */
const BUCKET = { rate: 6000, burst: 3000 };

interface Node {
  id: string;
  kind: EntityKind;
  side: Side;
  e: number;
  n: number;
  alt: number;
  ve: number;
  vn: number;
  comm: boolean;
  orbit?: { ce: number; cn: number; r: number; w: number; ph: number };
  tokens: number;
  seq: Map<string, number>;
}

interface GE {
  bad: boolean;
  recent: number; // 최근 손실률 EWMA
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function geo(nd: Node) {
  return {
    latDeg: ORIGIN.lat + nd.n / M_PER_DEG,
    lonDeg: ORIGIN.lon + nd.e / (M_PER_DEG * Math.cos((ORIGIN.lat * Math.PI) / 180)),
    altM: nd.alt,
  };
}

/** rx_time_us(필드 7, varint)를 직렬화된 LinkEnvelope 뒤에 붙인다. proto3는 뒤에 온 값이 이긴다 */
function appendRxTime(tx: Uint8Array, rxUs: number): Uint8Array {
  const tail: number[] = [0x38];
  let v = BigInt(Math.max(0, Math.round(rxUs)));
  do {
    let b = Number(v & 0x7fn);
    v >>= 7n;
    if (v > 0n) b |= 0x80;
    tail.push(b);
  } while (v > 0n);
  const out = new Uint8Array(tx.length + tail.length);
  out.set(tx);
  out.set(tail, tx.length);
  return out;
}

export class MockTraffic {
  readonly frameHz: number;
  readonly peerHz: number;
  readonly nodes: Node[] = [];
  frame = 0;
  /** 만든 프레임 수(종류별) */
  readonly counts = { outcome: 0, tx: 0, rx: 0, other: 0 };
  private readonly rnd: () => number;
  private readonly ge = new Map<string, GE>();
  private readonly byId = new Map<string, Node>();
  private readonly wire: boolean;
  private readonly replay: boolean;
  private deadAnnounced = false;
  private readonly deadId: string;

  constructor(
    private readonly emit: (f: BusFrame) => void,
    opts: MockOptions = {},
  ) {
    this.frameHz = opts.frameHz ?? 50;
    this.peerHz = opts.peerHz ?? 10;
    this.wire = opts.wire ?? false;
    this.replay = opts.replay ?? false;
    this.rnd = mulberry32(opts.seed ?? 1);
    const uavs = opts.uavs ?? 20;
    const add = (id: string, kind: EntityKind, side: Side, e: number, n: number, alt: number, comm: boolean) => {
      const nd: Node = { id, kind, side, e, n, alt, ve: 0, vn: 0, comm, tokens: BUCKET.burst, seq: new Map() };
      this.nodes.push(nd);
      this.byId.set(id, nd);
      return nd;
    };
    add(MOCK_GCS, EntityKind.GCS, Side.BLUE, 0, 0, 50, true);
    // 4개 편대가 서로 다른 원 궤도를 돈다. 2편대 궤도가 재밍 영역을 지난다
    const centers = [
      { ce: 2000, cn: 3000, r: 2500 },
      { ce: 4500, cn: 1000, r: 3000 },
      { ce: -3000, cn: -4000, r: 3500 },
      { ce: -1000, cn: 5000, r: 4000 },
    ];
    for (let i = 0; i < uavs; i++) {
      const g = centers[i % centers.length];
      const nd = add(`uav-${String(i + 1).padStart(3, "0")}`, EntityKind.UAV, Side.BLUE, 0, 0, 300 + 40 * (i % 5), true);
      nd.orbit = { ...g, w: 28 / g.r, ph: (2 * Math.PI * Math.floor(i / centers.length)) / Math.ceil(uavs / 4) + i };
    }
    this.deadId = uavs > MOCK_DEAD_UAV_INDEX ? `uav-${String(MOCK_DEAD_UAV_INDEX + 1).padStart(3, "0")}` : "";
    add(MOCK_JAM_SITE, EntityKind.JAMMER_SITE, Side.RED, JAM.e, JAM.n, 120, false);
    add("tgt-001", EntityKind.GROUND_TARGET, Side.RED, 7000, -2000, 80, false);
    add("tgt-002", EntityKind.GROUND_TARGET, Side.RED, 8500, 3500, 90, false);
    add("tgt-101", EntityKind.AIR_TARGET, Side.RED, 10000, 0, 1500, false);
    this.move(0);
  }

  get simTimeUs(): number {
    return Math.round((this.frame * 1e6) / this.frameHz);
  }

  stepFrame(): void {
    const tUs = this.simTimeUs;
    const tS = tUs / 1e6;
    const dt = 1 / this.frameHz;
    this.move(tS);
    for (const nd of this.nodes) nd.tokens = Math.min(BUCKET.burst, nd.tokens + BUCKET.rate * dt);

    const every = (hz: number, phase = 0) => Math.floor((this.frame + phase) * (hz / this.frameHz)) !== Math.floor((this.frame + phase - 1) * (hz / this.frameHz));
    const uavs = this.nodes.filter((n) => n.kind === EntityKind.UAV);
    uavs.forEach((u, i) => {
      if (!this.alive(u, tS)) return;
      if (every(this.peerHz, i)) this.sendPeerStatus(u, tUs);
      if (every(1, i * 3)) this.sendTrackShare(u, tUs);
      if (every(1, i * 7)) this.sendTaskStatus(u, tUs);
      if (every(2, i * 5)) this.sendSensorActivity(u, tUs);
    });
    const gcs = this.byId.get(MOCK_GCS)!;
    if (every(1 / 3)) {
      const u = uavs[Math.floor(this.rnd() * uavs.length)];
      this.sendTaskCommand(gcs, u.id, tUs);
    }
    // 20 s마다 전 기체에 경로 계획을 한꺼번에 보낸다 → GCS 큐 넘침
    if (every(1 / 20)) for (const u of uavs) this.sendRoutePlan(gcs, u.id, tUs);

    if (every(1)) this.publishTruth(tUs, tS);
    if (every(2)) this.publishStatus(tUs);
    if (every(1, 25)) this.publishLinkStates(tUs, tS);
    if (!this.deadAnnounced && this.deadId && tS >= MOCK_DEAD_AT_S) {
      this.deadAnnounced = true;
      this.put("truth/event/kill", TruthEventSchema, {
        header: { simTimeUs: BigInt(tUs), frame: BigInt(this.frame), source: "core-0" },
        event: { case: "kill", value: { entityId: this.deadId, cause: "impact" } },
      });
    }
    this.frame++;
  }

  // ---- 운동

  private move(tS: number): void {
    for (const nd of this.nodes) {
      const o = nd.orbit;
      if (!o) continue;
      const a = o.ph + o.w * tS;
      nd.e = o.ce + o.r * Math.cos(a);
      nd.n = o.cn + o.r * Math.sin(a);
      nd.ve = -o.r * o.w * Math.sin(a);
      nd.vn = o.r * o.w * Math.cos(a);
    }
  }

  private alive(nd: Node, tS: number): boolean {
    return !(nd.id === this.deadId && tS >= MOCK_DEAD_AT_S);
  }

  private jamActive(tS: number): boolean {
    const p = tS % JAM.periodS;
    return p >= JAM.onS && p < JAM.offS;
  }

  private inJam(nd: Node, tS: number): boolean {
    return this.jamActive(tS) && Math.hypot(nd.e - JAM.e, nd.n - JAM.n) < JAM.r;
  }

  private faulted(nd: Node, tS: number): boolean {
    const p = tS % 120;
    return nd.id === MOCK_FAULT_UAV && p >= MOCK_FAULT_WINDOW_S[0] && p < MOCK_FAULT_WINDOW_S[1];
  }

  private ridgeBlocked(a: Node, b: Node): boolean {
    const g = a.kind === EntityKind.GCS ? a : b.kind === EntityKind.GCS ? b : undefined;
    if (!g) return false;
    const o = g === a ? b : a;
    const de = o.e - g.e;
    const dn = o.n - g.n;
    const brg = ((Math.atan2(de, dn) * 180) / Math.PI + 360) % 360;
    return brg >= RIDGE.fromDeg && brg <= RIDGE.toDeg && Math.hypot(de, dn) > RIDGE.minM;
  }

  // ---- 링크 판정

  private judge(src: Node, dst: Node, tS: number, queued: boolean): { reason: DropReason; latUs: number } {
    const dist = Math.hypot(src.e - dst.e, src.n - dst.n, src.alt - dst.alt);
    const gcs = src.kind === EntityKind.GCS || dst.kind === EntityKind.GCS;
    const k = src.id < dst.id ? `${src.id}|${dst.id}` : `${dst.id}|${src.id}`;
    let ge = this.ge.get(k);
    if (!ge) this.ge.set(k, (ge = { bad: false, recent: 0 }));
    // Gilbert-Elliott 상태 전이
    if (ge.bad ? this.rnd() < 0.25 : this.rnd() < 0.01) ge.bad = !ge.bad;

    let reason = DropReason.NONE;
    if (!this.alive(dst, tS)) reason = DropReason.NODE_DEAD;
    else if (this.faulted(src, tS) || this.faulted(dst, tS)) reason = DropReason.FAULT_INJECTED;
    else if (this.inJam(src, tS) || this.inJam(dst, tS)) reason = DropReason.JAMMED;
    else if (dist > (gcs ? RANGE_GCS_M : RANGE_P2P_M)) reason = DropReason.OUT_OF_RANGE;
    else if (this.ridgeBlocked(src, dst)) reason = DropReason.NO_LOS;
    else if (queued) reason = DropReason.QUEUE_OVERFLOW;
    else if (this.rnd() < (ge.bad ? 0.6 : 0.002)) reason = DropReason.BURST_LOSS;

    ge.recent = 0.95 * ge.recent + (reason === DropReason.NONE ? 0 : 0.05);
    const jitter = -Math.log(1 - this.rnd()) * 3000;
    const latUs = 2000 + (dist / C_MPS) * 1e6 + jitter + (gcs ? 10_000 : 0);
    return { reason, latUs };
  }

  // ---- 메시지

  private send<S extends DescMessage>(
    src: Node,
    dsts: string[],
    iface: L1Interface,
    schema: S,
    init: MessageInitShape<S>,
    tUs: number,
    priority = 5,
  ): void {
    const tS = tUs / 1e6;
    const msgType = schema.typeName;
    const key = `swarm/${src.id}/tx/${IFACE_KEY[iface]}/${shortType(msgType)}`;
    const seq = (src.seq.get(key) ?? 0) + 1;
    src.seq.set(key, seq);
    const header = { simTimeUs: BigInt(tUs), frame: BigInt(this.frame), source: src.id, seq };
    const payload = toBinary(schema, create(schema, { ...init, header } as MessageInitShape<S>));
    const envBytes = toBinary(LinkEnvelopeSchema, create(LinkEnvelopeSchema, { header, dst: dsts, iface, msgType, payload, priority }));
    const encoding = `${PROTOBUF_ENCODING_PREFIX}${LinkEnvelopeSchema.typeName}`;
    this.out({ key, encoding, payload: envBytes });
    this.counts.tx++;

    // 토큰 버킷: 모자라면 이 메시지 전체가 큐에서 버려진다
    const queued = src.tokens < payload.length;
    if (!queued) src.tokens -= payload.length;

    // 브로드캐스트 수신 대상은 같은 편 무전기 엔티티 전원이다 (DEC-032)
    const targets = dsts.length ? dsts.map((d) => this.byId.get(d)!).filter(Boolean) : this.nodes.filter((n) => n.comm && n.side === src.side && n !== src);
    for (const dst of targets) {
      const { reason, latUs } = this.judge(src, dst, tS, queued);
      const delivered = reason === DropReason.NONE;
      const rxUs = delivered ? tUs + latUs : 0;
      this.put(`link/outcome/${src.id}/${dst.id}`, LinkOutcomeSchema, {
        src: src.id,
        dst: dst.id,
        seq,
        iface,
        msgType,
        sizeBytes: payload.length,
        outcome: delivered ? LinkOutcomeKind.DELIVERED : LinkOutcomeKind.DROPPED,
        reason,
        txTimeUs: BigInt(tUs),
        rxTimeUs: BigInt(Math.round(rxUs)),
      });
      this.counts.outcome++;
      if (delivered) {
        this.out({ key: `swarm/${dst.id}/rx/${IFACE_KEY[iface]}/${shortType(msgType)}`, encoding, payload: appendRxTime(envBytes, rxUs) });
        this.counts.rx++;
      }
    }
  }

  private kin(nd: Node) {
    return { position: geo(nd), velocityNedMps: { x: nd.vn, y: nd.ve, z: 0 } };
  }

  private sendPeerStatus(u: Node, tUs: number): void {
    this.send(u, [], L1Interface.P2P, PeerStatusSchema, { kinematics: this.kin(u), groupId: `grp-${u.id.slice(-1)}`, energyFrac: 0.8 }, tUs);
  }

  private sendTrackShare(u: Node, tUs: number): void {
    const t = this.byId.get("tgt-001")!;
    this.send(u, [], L1Interface.P2P, TrackShareSchema, { trackId: `trk-${u.id}`, targetId: t.id, position: geo(t), kind: EntityKind.GROUND_TARGET, observedTimeUs: BigInt(tUs) }, tUs, 3);
  }

  private sendTaskStatus(u: Node, tUs: number): void {
    this.send(u, [MOCK_GCS], L1Interface.C2, TaskStatusSchema, { taskId: `task-${u.id}`, state: CommandState.EXECUTING, progress: (tUs / 1e6 / 300) % 1 }, tUs, 1);
  }

  private sendSensorActivity(u: Node, tUs: number): void {
    this.send(u, [MOCK_GCS], L1Interface.MS, SensorActivitySchema, { payloadId: "cam0", active: true, hfovDeg: 40, vfovDeg: 30, maxRangeM: 5000 }, tUs, 4);
  }

  private sendTaskCommand(g: Node, to: string, tUs: number): void {
    this.send(g, [to], L1Interface.C2, TaskCommandSchema, { taskId: `task-${to}`, assignees: [to], task: { case: "hold", value: {} } }, tUs, 0);
  }

  private sendRoutePlan(g: Node, to: string, tUs: number): void {
    const wp = Array.from({ length: 12 }, (_, i) => ({ position: { latDeg: ORIGIN.lat + i * 0.001, lonDeg: ORIGIN.lon, altM: 400 } }));
    this.send(g, [to], L1Interface.MP, RoutePlanSchema, { routeId: `route-${to}`, entityId: to, waypoints: wp }, tUs, 2);
  }

  // ---- 지상 진실·상태

  private publishTruth(tUs: number, tS: number): void {
    this.put("truth/state", TruthFrameSchema, {
      header: { simTimeUs: BigInt(tUs), frame: BigInt(this.frame), source: "core-0" },
      entities: this.nodes.map((nd) => ({
        id: nd.id,
        kind: nd.kind,
        side: nd.side,
        alive: this.alive(nd, tS),
        kinematics: this.kin(nd),
        energyFrac: 0.8,
      })),
    });
  }

  private publishStatus(tUs: number): void {
    this.put("sim/ctrl/status", SimStatusSchema, {
      state: SimRunState.RUNNING,
      mode: RunMode.REALTIME,
      simTimeUs: BigInt(tUs),
      frame: BigInt(this.frame),
      frameHz: this.frameHz,
      rateTarget: 1,
      rateActual: 1,
      entityCount: this.nodes.length,
      scenarioName: "mock-traffic",
      replay: this.replay,
    });
  }

  private publishLinkStates(tUs: number, tS: number): void {
    const comm = this.nodes.filter((n) => n.comm);
    for (let i = 0; i < comm.length; i++) {
      for (let j = i + 1; j < comm.length; j++) {
        const [a, b] = comm[i].id < comm[j].id ? [comm[i], comm[j]] : [comm[j], comm[i]];
        const ge = this.ge.get(`${a.id}|${b.id}`);
        const dist = Math.hypot(a.e - b.e, a.n - b.n, a.alt - b.alt);
        const jammed = this.inJam(a, tS) || this.inJam(b, tS);
        const los = !this.ridgeBlocked(a, b);
        const range = a.kind === EntityKind.GCS || b.kind === EntityKind.GCS ? RANGE_GCS_M : RANGE_P2P_M;
        const lossRate = ge?.recent ?? 0;
        const down = jammed || !los || dist > range || !this.alive(a, tS) || !this.alive(b, tS) || this.faulted(a, tS) || this.faulted(b, tS);
        this.put(`link/state/${a.id}/${b.id}`, LinkStateSchema, {
          header: { simTimeUs: BigInt(tUs), frame: BigInt(this.frame), source: "datalink-0" },
          a: a.id,
          b: b.id,
          state: down ? LinkStateKind.DOWN : lossRate > 0.1 ? LinkStateKind.DEGRADED : LinkStateKind.UP,
          snrDb: 40 - 20 * Math.log10(Math.max(dist, 1) / 100),
          lossRate,
          los,
          jammed,
        });
      }
    }
  }

  private put<S extends DescMessage>(key: string, schema: S, init: MessageInitShape<S>): void {
    const payload = toBinary(schema, create(schema, init));
    if (!key.startsWith("link/outcome/")) this.counts.other++;
    this.out({ key, encoding: `${PROTOBUF_ENCODING_PREFIX}${schema.typeName}`, payload });
  }

  private out(f: BusFrame): void {
    if (this.wire) {
      // 브리지 경로와 같이 바이트열로 만들었다가 다시 푼다
      this.emit(decodeFrame(encodeFrame(f)));
    } else {
      this.emit(f);
    }
  }
}
