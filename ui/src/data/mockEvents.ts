// IMP-UI-063: 목 truth 이벤트·센서 (DEC-046). Core 발행자(WP1 통합) 전에 화면을 확인하려고
// 60 s 주기 각본으로 재밍 구역·발사체·FPV·SensorActivity를 만든다. 결정론(시각만의 함수, 발사 순간 위치를 기억)
//   τ= 2 s  site-01 원형 재밍 구역 켜짐(반경 4 km, 0–3000 m)     τ=40 s 꺼짐
//   τ= 5 s  uav-019 다각형 재밍 구역 켜짐(상한 없음)               τ=50 s 꺼짐
//   τ=10 s  uav-001 → tgt-001 미사일 launch+spawn, τ=22 s impact(살상반경 30 m)
//   τ=15 s  uav-002 → tgt-002 FPV spawn, τ=27 s kill(ground, impact 없음)
// SensorActivity: uav-001 cam0(진행 방향 아래 35°, 40°×30°, 6 km)를 1 s마다. τ=30–35 s는 active=false(고장 흉내)
import type { MessageInitShape } from "@bufbuild/protobuf";
import { create, toBinary } from "@bufbuild/protobuf";
import type { EntityState } from "../gen/swarm/v1/entity_pb";
import { EntityKind, EntityStateSchema, Side } from "../gen/swarm/v1/entity_pb";
import type { LinkEnvelope } from "../gen/swarm/v1/link_pb";
import { LinkEnvelopeSchema } from "../gen/swarm/v1/link_pb";
import { SensorActivitySchema } from "../gen/swarm/v1/ms_pb";
import { L1Interface } from "../gen/swarm/v1/options_pb";
import type { TruthEvent, TruthFrame } from "../gen/swarm/v1/truth_pb";
import { TruthEventSchema } from "../gen/swarm/v1/truth_pb";
import type { GeoPos } from "../model/truthEvents";
import { offsetNed } from "../model/sensorFov";

export const MOCK_EVENT_PERIOD_S = 60;

interface Flight {
  id: string;
  kind: EntityKind;
  shooter: string;
  target: string;
  t0: number;
  t1: number;
  /** 종료 방식 */
  end: "impact" | "kill";
  from: GeoPos;
  to: GeoPos;
  arcM: number;
}

const US = 1_000_000;
const ZONE_POLY_OWNER = "uav-019";

const pos = (e: EntityState | undefined): GeoPos | null => {
  const p = e?.kinematics?.position;
  return p ? { lat: p.latDeg, lon: p.lonDeg, alt: p.altM } : null;
};

/** 발사체 위치·속도: 직선 + 포물선 고도 */
function flyAt(f: Flight, t: number): { p: GeoPos; v: [number, number, number] } {
  const s = Math.min(Math.max((t - f.t0) / (f.t1 - f.t0), 0), 1);
  const lerp = (a: number, b: number) => a + (b - a) * s;
  const p = { lat: lerp(f.from.lat, f.to.lat), lon: lerp(f.from.lon, f.to.lon), alt: lerp(f.from.alt, f.to.alt) + 4 * f.arcM * s * (1 - s) };
  const dur = f.t1 - f.t0;
  const R = 6378137, D = Math.PI / 180;
  const vn = ((f.to.lat - f.from.lat) * D * R) / dur;
  const ve = ((f.to.lon - f.from.lon) * D * R * Math.cos(f.from.lat * D)) / dur;
  const vd = -((f.to.alt - f.from.alt) / dur + (4 * f.arcM * (1 - 2 * s)) / dur);
  return { p, v: [vn, ve, vd] };
}

export class MockEvents {
  private flights = new Map<string, Flight>();
  private lastSensorS = -Infinity;

  constructor(private readonly gcs = "gcs-01") {}

  reset(): void {
    this.flights.clear();
    this.lastSensorS = -Infinity;
  }

  /**
   * (prevS, nowS] 구간의 이벤트를 만들고, 비행 중인 발사체를 frame.entities에 넣는다.
   * frame은 시각 nowS의 TruthFrame(기체·표적 위치를 여기서 읽는다)
   */
  step(prevS: number, nowS: number, frame: TruthFrame): TruthEvent[] {
    const out: TruthEvent[] = [];
    const byId = new Map(frame.entities.map((e) => [e.id, e]));
    const frameNo = frame.header?.frame ?? 0n;
    const ev = (t: number, src: string, event: MessageInitShape<typeof TruthEventSchema>["event"]) =>
      out.push(create(TruthEventSchema, { header: { simTimeUs: BigInt(Math.round(t * US)), frame: frameNo, source: src }, event }));
    const P = MOCK_EVENT_PERIOD_S;
    const c0 = Math.floor(Math.max(prevS, 0) / P);
    const c1 = Math.floor(nowS / P);
    for (let c = c0; c <= c1; c++) {
      const at = (tau: number) => {
        const t = c * P + tau;
        return t > prevS && t <= nowS ? t : null;
      };
      const n = String(c + 1).padStart(2, "0");
      let t: number | null;
      if ((t = at(2)) !== null) {
        const site = pos(byId.get("site-01"));
        if (site)
          ev(t, "site-01", {
            case: "jamZone",
            value: { owner: "site-01", active: true, area: { shape: { case: "circle", value: { center: { latDeg: site.lat, lonDeg: site.lon, altM: 0 }, radiusM: 4000 } }, minAltM: 0, maxAltM: 3000 } },
          });
      }
      if ((t = at(40)) !== null) ev(t, "site-01", { case: "jamZone", value: { owner: "site-01", active: false } });
      if ((t = at(5)) !== null) {
        const o = pos(byId.get(ZONE_POLY_OWNER));
        if (o) {
          const vs = [[2500, -1500], [2500, 1500], [0, 3000], [-2500, 1500], [-2500, -1500]].map(([dn, de]) => {
            const g = offsetNed(o, dn, de, 0);
            return { latDeg: g.lat, lonDeg: g.lon, altM: 0 };
          });
          ev(t, ZONE_POLY_OWNER, {
            case: "jamZone",
            value: { owner: ZONE_POLY_OWNER, active: true, area: { shape: { case: "polygon", value: { vertices: vs } }, minAltM: 500, maxAltM: 0 } },
          });
        }
      }
      if ((t = at(50)) !== null) ev(t, ZONE_POLY_OWNER, { case: "jamZone", value: { owner: ZONE_POLY_OWNER, active: false } });

      const launch = (tau: number, id: string, kind: EntityKind, shooter: string, target: string, dur: number, end: Flight["end"], arcM: number) => {
        const tl = at(tau);
        if (tl === null) return;
        const from = pos(byId.get(shooter)), to = pos(byId.get(target));
        if (!from || !to) return;
        const f: Flight = { id, kind, shooter, target, t0: tl, t1: tl + dur, end, from, to, arcM };
        this.flights.set(id, f);
        const st = this.state(f, tl, true);
        if (kind === EntityKind.MISSILE) ev(tl, shooter, { case: "launch", value: { shooter, weaponEntity: id, targetId: target } });
        ev(tl, shooter, { case: "spawn", value: { entity: st } });
      };
      launch(10, `wpn-uav-001-${n}`, EntityKind.MISSILE, "uav-001", "tgt-001", 12, "impact", 400);
      launch(15, `wpn-uav-002-${n}`, EntityKind.FPV, "uav-002", "tgt-002", 12, "kill", 150);
    }
    // 비행 중·종료
    for (const [id, f] of this.flights) {
      if (f.t1 <= nowS) {
        if (f.t1 > prevS) {
          if (f.end === "impact") {
            ev(f.t1, id, {
              case: "impact",
              value: { weaponEntity: id, position: { latDeg: f.to.lat, lonDeg: f.to.lon, altM: f.to.alt }, lethalRadiusM: 30, killed: [] },
            });
            ev(f.t1, id, { case: "kill", value: { entityId: id, cause: "impact" } });
          } else {
            ev(f.t1, id, { case: "kill", value: { entityId: id, cause: "ground" } });
          }
          // Core처럼 alive=false를 한 번 내고 다음 프레임부터 뺀다
          frame.entities.push(this.state(f, f.t1, false));
        }
        this.flights.delete(id);
        continue;
      }
      if (f.t0 <= nowS) frame.entities.push(this.state(f, nowS, true));
    }
    return out;
  }

  /** uav-001 cam0 SensorActivity(1 s 주기). 보낼 때가 아니면 null */
  sensor(nowS: number, frame: TruthFrame): LinkEnvelope | null {
    if (nowS - this.lastSensorS < 1 && nowS >= this.lastSensorS) return null;
    const uav = frame.entities.find((e) => e.id === "uav-001");
    const v = uav?.kinematics?.velocityNedMps;
    if (!uav || !v) return null;
    this.lastSensorS = nowS;
    const h = Math.atan2(v.y, v.x);
    const dep = (35 * Math.PI) / 180;
    const tau = nowS % MOCK_EVENT_PERIOD_S;
    const simTimeUs = BigInt(Math.round(nowS * US));
    const frameNo = frame.header?.frame ?? 0n;
    const act = create(SensorActivitySchema, {
      header: { simTimeUs, frame: frameNo, source: "uav-001" },
      payloadId: "cam0",
      active: !(tau >= 30 && tau < 35),
      boresightNed: { x: Math.cos(dep) * Math.cos(h), y: Math.cos(dep) * Math.sin(h), z: Math.sin(dep) },
      hfovDeg: 40,
      vfovDeg: 30,
      maxRangeM: 6000,
    });
    return create(LinkEnvelopeSchema, {
      header: { simTimeUs, frame: frameNo, source: "uav-001" },
      dst: [this.gcs],
      iface: L1Interface.MS,
      msgType: SensorActivitySchema.typeName,
      payload: toBinary(SensorActivitySchema, act),
      rxTimeUs: simTimeUs,
    });
  }

  private state(f: Flight, t: number, alive: boolean): EntityState {
    const { p, v } = flyAt(f, t);
    return create(EntityStateSchema, {
      id: f.id,
      kind: f.kind,
      side: Side.BLUE,
      alive,
      energyFrac: 1,
      kinematics: {
        position: { latDeg: p.lat, lonDeg: p.lon, altM: p.alt },
        velocityNedMps: { x: v[0], y: v[1], z: v[2] },
        attitude: { w: 1, x: 0, y: 0, z: 0 },
      },
    });
  }
}
