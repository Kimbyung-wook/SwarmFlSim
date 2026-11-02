// IMP-UI-045: 기체별 매개변수 모델 (REQ-CFG-003, DEC-035)
// sim/param/<entity>/<owner>의 EntityParams를 보관하고, 선택한 기체들의 항목을 계층별로 묶고,
// 입력을 ParamSpec(형식·min/max)으로 검사해 SimCommand.set_params를 만든다. Cesium·React에 의존하지 않는다.
// 적용 여부는 EntityParams.values가 바뀌었을 때만 인정한다. 보낸 값은 "대기"로만 표시한다.
import { create, toJson } from "@bufbuild/protobuf";
import type { JsonObject, JsonValue } from "@bufbuild/protobuf";
import { ValueSchema } from "@bufbuild/protobuf/wkt";
import { ParamLayer } from "../gen/swarm/v1/entity_pb";
import type { ParamSpec } from "../gen/swarm/v1/entity_pb";
import type { EntityParams } from "../gen/swarm/v1/sim_pb";
import { ParamOwner, SimCommandSchema } from "../gen/swarm/v1/sim_pb";
import type { SimCommand } from "../gen/swarm/v1/sim_pb";

export type ParamScalar = number | string | boolean;
export type ParamType = "number" | "string" | "boolean";

export const OWNERS = [ParamOwner.DYNAMICS, ParamOwner.FA, ParamOwner.MA] as const;

export const OWNER_LABEL: Record<number, string> = {
  [ParamOwner.DYNAMICS]: "동역학",
  [ParamOwner.FA]: "FA",
  [ParamOwner.MA]: "MA",
};

export const LAYERS = [
  ParamLayer.AIRFRAME,
  ParamLayer.CONTROL,
  ParamLayer.GUIDANCE,
  ParamLayer.BEHAVIOR,
  ParamLayer.DECISION,
] as const;

export const LAYER_LABEL: Record<number, string> = {
  [ParamLayer.AIRFRAME]: "기체",
  [ParamLayer.CONTROL]: "제어",
  [ParamLayer.GUIDANCE]: "유도",
  [ParamLayer.BEHAVIOR]: "행위",
  [ParamLayer.DECISION]: "결정",
  [ParamLayer.UNSPECIFIED]: "기타",
};

/** EntityParams.rejected[].reason (docs/10_contracts.md §3) */
export const REJECT_LABEL: Record<string, string> = {
  unknown: "선언되지 않은 이름",
  type: "형식이 맞지 않음",
  range: "허용 범위를 벗어남",
  not_runtime: "실행 중에는 바꿀 수 없음",
};

export function rejectLabel(reason: string): string {
  return REJECT_LABEL[reason] ?? reason;
}

function scalar(v: JsonValue | undefined): ParamScalar | undefined {
  return typeof v === "number" || typeof v === "string" || typeof v === "boolean" ? v : undefined;
}

/** ParamSpec.default_value (google.protobuf.Value) → number | string | boolean */
export function defaultOf(spec: ParamSpec): ParamScalar | undefined {
  return spec.defaultValue ? scalar(toJson(ValueSchema, spec.defaultValue)) : undefined;
}

/** 형식은 기본값의 종류가 정한다. 기본값이 없으면 숫자로 본다 */
export function typeOf(spec: ParamSpec): ParamType {
  const d = defaultOf(spec);
  return typeof d === "string" ? "string" : typeof d === "boolean" ? "boolean" : "number";
}

const ownerKey = (entityId: string, owner: ParamOwner) => `${entityId}/${owner}`;

/** 받은 EntityParams 보관소. 기체·소유자별 최신 하나 */
export class ParamStore {
  private readonly map = new Map<string, EntityParams>();
  /** 받을 때마다 1 증가 */
  version = 0;

  onParams(p: EntityParams): void {
    this.map.set(ownerKey(p.entityId, p.owner), p);
    this.version++;
  }

  get(entityId: string, owner: ParamOwner): EntityParams | undefined {
    return this.map.get(ownerKey(entityId, owner));
  }

  /** 기체의 선언이 하나라도 있는가 */
  has(entityId: string): boolean {
    return OWNERS.some((o) => this.map.has(ownerKey(entityId, o)));
  }
}

export interface ParamTarget {
  entityId: string;
  /** 적용 중인 값. 아직 받지 못했으면 undefined */
  value: ParamScalar | undefined;
  /** 직전 변경에서 거부된 사유 코드 */
  rejected?: string;
}

export interface ParamRow {
  /** owner:name */
  key: string;
  owner: ParamOwner;
  spec: ParamSpec;
  type: ParamType;
  defaultValue: ParamScalar | undefined;
  targets: ParamTarget[];
  /** 모든 대상의 값이 같으면 그 값. 다르면 undefined */
  common: ParamScalar | undefined;
  mixed: boolean;
  /** 대상 중 하나라도 거부 사유가 있으면 첫 사유 */
  rejected?: { entityId: string; reason: string };
}

export interface ParamGroup {
  layer: ParamLayer;
  rows: ParamRow[];
}

/**
 * 선택한 기체들의 매개변수 항목. 계층 순서로 묶는다.
 * 여러 기체면 소유자와 이름이 모두 같은 항목만 한 줄로 합친다(같은 이름을 한꺼번에 설정).
 */
export function composeGroups(store: ParamStore, ids: readonly string[]): ParamGroup[] {
  if (ids.length === 0) return [];
  const rows: ParamRow[] = [];
  for (const owner of OWNERS) {
    const per = ids.map((id) => store.get(id, owner));
    if (per.some((p) => p === undefined)) continue;
    const first = per[0] as EntityParams;
    for (const spec of first.specs) {
      const targets: ParamTarget[] = [];
      let ok = true;
      for (const p of per as EntityParams[]) {
        const s = p.specs.find((x) => x.name === spec.name);
        if (!s) {
          ok = false;
          break;
        }
        const rej = p.rejected.find((r) => r.name === spec.name);
        targets.push({ entityId: p.entityId, value: scalar(p.values?.[spec.name]), rejected: rej?.reason });
      }
      if (!ok) continue;
      const vals = targets.map((t) => t.value);
      const mixed = vals.some((v) => v !== vals[0]);
      const rej = targets.find((t) => t.rejected !== undefined);
      rows.push({
        key: `${owner}:${spec.name}`,
        owner,
        spec,
        type: typeOf(spec),
        defaultValue: defaultOf(spec),
        targets,
        common: mixed ? undefined : vals[0],
        mixed,
        rejected: rej ? { entityId: rej.entityId, reason: rej.rejected as string } : undefined,
      });
    }
  }
  return LAYERS.concat(ParamLayer.UNSPECIFIED as never)
    .map((layer) => ({ layer: layer as ParamLayer, rows: rows.filter((r) => r.spec.layer === layer) }))
    .filter((g) => g.rows.length > 0);
}

export type ParseResult = { ok: true; value: ParamScalar } | { ok: false; error: string };

/** 입력 문자열(또는 체크 상태)을 ParamSpec 형식·min/max로 검사한다 */
export function parseInput(spec: ParamSpec, input: string | boolean): ParseResult {
  const type = typeOf(spec);
  if (type === "boolean") {
    if (typeof input === "boolean") return { ok: true, value: input };
    if (input === "true") return { ok: true, value: true };
    if (input === "false") return { ok: true, value: false };
    return { ok: false, error: "참/거짓이어야 한다" };
  }
  if (typeof input === "boolean") return { ok: false, error: "형식이 맞지 않음" };
  if (type === "string") return { ok: true, value: input };
  const t = input.trim();
  const n = Number(t);
  if (t === "" || !Number.isFinite(n)) return { ok: false, error: "숫자를 입력한다" };
  if (spec.min !== undefined && n < spec.min) return { ok: false, error: `${spec.min} 이상이어야 한다` };
  if (spec.max !== undefined && n > spec.max) return { ok: false, error: `${spec.max} 이하여야 한다` };
  return { ok: true, value: n };
}

export function formatValue(v: ParamScalar | undefined, unit = ""): string {
  if (v === undefined) return "—";
  const s = typeof v === "boolean" ? (v ? "참" : "거짓") : String(v);
  return unit ? `${s} ${unit}` : s;
}

export function rangeText(spec: ParamSpec): string {
  if (typeOf(spec) !== "number") return "";
  if (spec.min !== undefined && spec.max !== undefined) return `${spec.min} ~ ${spec.max}`;
  if (spec.min !== undefined) return `≥ ${spec.min}`;
  if (spec.max !== undefined) return `≤ ${spec.max}`;
  return "";
}

/**
 * SimCommand.set_params. 기체·소유자마다 하나씩 만든다. values에는 바꿀 이름만 담는다.
 */
export function setParamsCommands(
  issuer: string,
  entityIds: readonly string[],
  owner: ParamOwner,
  values: Record<string, ParamScalar>,
): SimCommand[] {
  if (Object.keys(values).length === 0) throw new Error("바꿀 매개변수가 없다");
  if (entityIds.length === 0) throw new Error("대상 기체가 없다");
  const json: JsonObject = { ...values };
  return entityIds.map((entityId) =>
    create(SimCommandSchema, { issuer, cmd: { case: "setParams", value: { entityId, owner, values: json } } }),
  );
}

/** 이 행을 기본값으로 되돌리는 값. 이미 모든 대상이 기본값이면 null */
export function resetValue(row: ParamRow): ParamScalar | null {
  if (row.defaultValue === undefined) return null;
  return row.targets.every((t) => t.value === row.defaultValue) ? null : row.defaultValue;
}

/** 보낸 값이 적용됐는가(모든 대상의 values가 보낸 값과 같다) */
export function applied(row: ParamRow, sent: ParamScalar): boolean {
  return row.targets.every((t) => t.value === sent);
}
