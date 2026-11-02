// IMP-UI-046: 목 소스의 기체별 매개변수 소유자 (REQ-CFG-003, DEC-035)
// 동역학·FA·MA가 선언과 적용 값을 EntityParams로 내보내고, SimCommand.set_params를 검사해 적용·거부하는 것을 흉내 낸다.
// 검사 규칙은 계약(docs/10_contracts.md)과 같다: unknown | type | range | not_runtime. 조용히 무시하지 않는다.
import { create, fromJson } from "@bufbuild/protobuf";
import { ValueSchema } from "@bufbuild/protobuf/wkt";
import type { JsonObject } from "@bufbuild/protobuf";
import { ParamLayer, ParamSpecSchema } from "../gen/swarm/v1/entity_pb";
import type { ParamSpec } from "../gen/swarm/v1/entity_pb";
import { EntityParamsSchema, ParamOwner } from "../gen/swarm/v1/sim_pb";
import type { EntityParams } from "../gen/swarm/v1/sim_pb";

function spec(o: {
  name: string;
  layer: ParamLayer;
  def: number | string | boolean;
  unit?: string;
  min?: number;
  max?: number;
  choices?: string[];
  description: string;
  runtime?: boolean;
}): ParamSpec {
  return create(ParamSpecSchema, {
    name: o.name,
    layer: o.layer,
    defaultValue: fromJson(ValueSchema, o.def),
    unit: o.unit ?? "",
    min: o.min,
    max: o.max,
    choices: o.choices ?? [],
    description: o.description,
    runtime: o.runtime ?? true,
  });
}

const DYNAMICS: ParamSpec[] = [
  spec({ name: "mass_kg", layer: ParamLayer.AIRFRAME, def: 11, unit: "kg", min: 1, max: 100, description: "기체 질량", runtime: false }),
  spec({ name: "v_max_mps", layer: ParamLayer.AIRFRAME, def: 45, unit: "m/s", min: 10, max: 120, description: "최대 속도" }),
  spec({ name: "bank_max_deg", layer: ParamLayer.AIRFRAME, def: 40, unit: "deg", min: 5, max: 75, description: "뱅크각 한계" }),
  spec({ name: "kp_roll", layer: ParamLayer.CONTROL, def: 2.4, min: 0, max: 20, description: "롤 루프 비례 이득" }),
  spec({ name: "kp_speed", layer: ParamLayer.CONTROL, def: 0.8, min: 0, max: 10, description: "속도 루프 비례 이득" }),
];

const FA: ParamSpec[] = [
  spec({ name: "lookahead_s", layer: ParamLayer.GUIDANCE, def: 8, unit: "s", min: 1, max: 60, description: "경로 추종 전방 주시 시간" }),
  spec({ name: "loiter_radius_m", layer: ParamLayer.GUIDANCE, def: 600, unit: "m", min: 100, max: 5000, description: "기본 선회 반경" }),
  spec({ name: "racetrack_guidance", layer: ParamLayer.GUIDANCE, def: "dubins", choices: ["dubins", "vector_field"], description: "레이스트랙 유도: dubins | vector_field (DEC-034)" }),
  spec({ name: "terrain_follow", layer: ParamLayer.GUIDANCE, def: false, description: "지형 추종 비행" }),
];

const MA: ParamSpec[] = [
  spec({ name: "separation_m", layer: ParamLayer.BEHAVIOR, def: 150, unit: "m", min: 20, max: 2000, description: "편대 안 최소 이격" }),
  spec({ name: "formation", layer: ParamLayer.BEHAVIOR, def: "line", description: "편대 형상 이름", runtime: true }),
  spec({ name: "aggressiveness", layer: ParamLayer.DECISION, def: 0.5, min: 0, max: 1, description: "교전 적극성" }),
  spec({ name: "autonomous_strike", layer: ParamLayer.DECISION, def: false, description: "표적 자동 지정 허용", runtime: false }),
];

const SPECS: Record<number, ParamSpec[]> = {
  [ParamOwner.DYNAMICS]: DYNAMICS,
  [ParamOwner.FA]: FA,
  [ParamOwner.MA]: MA,
};
const PLUGIN: Record<number, string> = { [ParamOwner.DYNAMICS]: "mock_fixed_wing", [ParamOwner.FA]: "mock_fa", [ParamOwner.MA]: "mock_ma" };
const OWNER_KEY: Record<number, string> = { [ParamOwner.DYNAMICS]: "dynamics", [ParamOwner.FA]: "fa", [ParamOwner.MA]: "ma" };

export const MOCK_OWNERS = [ParamOwner.DYNAMICS, ParamOwner.FA, ParamOwner.MA] as const;

export function paramKey(entityId: string, owner: ParamOwner): string {
  return `sim/param/${entityId}/${OWNER_KEY[owner]}`;
}

function defaultsOf(specs: ParamSpec[]): JsonObject {
  const out: JsonObject = {};
  for (const s of specs) {
    const k = s.defaultValue?.kind;
    if (k && k.case !== undefined && k.case !== "nullValue" && k.case !== "structValue" && k.case !== "listValue") out[s.name] = k.value;
  }
  return out;
}

function typeOk(s: ParamSpec, v: unknown): boolean {
  const k = s.defaultValue?.kind.case;
  return k === "numberValue" ? typeof v === "number" && Number.isFinite(v) : k === "stringValue" ? typeof v === "string" : typeof v === "boolean";
}

/** 기체 한 대의 소유자별 매개변수 상태 */
export class MockParams {
  private readonly values = new Map<string, JsonObject>();
  private readonly rejected = new Map<string, { name: string; reason: string }[]>();
  /** 시나리오 시작값(적재 직후 적용). 항목 검사는 set_params와 같다 */
  constructor(private readonly start: Record<string, Partial<Record<ParamOwner, JsonObject>>> = {}) {}

  private k(id: string, owner: ParamOwner) {
    return `${id}/${owner}`;
  }

  private ensure(id: string, owner: ParamOwner): JsonObject {
    const key = this.k(id, owner);
    let v = this.values.get(key);
    if (!v) {
      v = defaultsOf(SPECS[owner]);
      this.values.set(key, v);
      this.rejected.set(key, []);
      const init = this.start[id]?.[owner];
      if (init) this.apply(id, owner, init, true);
    }
    return v;
  }

  /** 검사해 적용한다. 거부한 항목은 사유와 함께 남긴다. runtime=false는 시작값에서만 허용 */
  apply(id: string, owner: ParamOwner, req: JsonObject, atLoad = false): { name: string; reason: string }[] {
    const v = this.ensure(id, owner);
    const rej: { name: string; reason: string }[] = [];
    for (const [name, val] of Object.entries(req)) {
      const s = SPECS[owner].find((x) => x.name === name);
      if (!s) rej.push({ name, reason: "unknown" });
      else if (!typeOk(s, val)) rej.push({ name, reason: "type" });
      else if (typeof val === "string" && s.choices.length > 0 && !s.choices.includes(val)) rej.push({ name, reason: "choice" });
      else if (typeof val === "number" && ((s.min !== undefined && val < s.min) || (s.max !== undefined && val > s.max))) rej.push({ name, reason: "range" });
      else if (!atLoad && !s.runtime) rej.push({ name, reason: "not_runtime" });
      else if (name === "kp_roll" && typeof val === "number" && val > 10) rej.push({ name, reason: "range" }); // 목 전용: 소유자가 선언(max 20)보다 엄격하게 거부하는 경우. GUI 거부 표시 확인용
      else v[name] = val;
    }
    this.rejected.set(this.k(id, owner), rej);
    return rej;
  }

  snapshot(id: string, owner: ParamOwner, simTimeUs: bigint): EntityParams {
    const v = this.ensure(id, owner);
    return create(EntityParamsSchema, {
      entityId: id,
      owner,
      plugin: PLUGIN[owner],
      specs: SPECS[owner],
      values: { ...v },
      rejected: this.rejected.get(this.k(id, owner)) ?? [],
      simTimeUs,
    });
  }
}
