// IMP-UI-015: 수신 상태 보관소. 프레임마다 React를 다시 그리지 않도록 최신 프레임·궤적을 여기에 두고
// 지도는 렌더 루프에서, 패널은 낮은 주기로 읽는다 (REQ-UI-001)
import type { SimStatus } from "../gen/swarm/v1/sim_pb";
import type { TruthFrame } from "../gen/swarm/v1/truth_pb";
import type { FrameView } from "./entityView";
import { toFrameView } from "./entityView";
import type { TrailOptions } from "./trails";
import { TrailStore } from "./trails";

export class LiveState {
  frame: FrameView = { frame: 0n, simTimeUs: 0n, entities: [] };
  status: SimStatus | null = null;
  readonly trails: TrailStore;
  /** 프레임을 받을 때마다 1 증가 */
  version = 0;
  private byId = new Map<string, FrameView["entities"][number]>();

  constructor(trail?: TrailOptions) {
    this.trails = new TrailStore(trail);
  }

  onTruth(f: TruthFrame): void {
    this.frame = toFrameView(f);
    this.byId = new Map(this.frame.entities.map((e) => [e.id, e]));
    this.trails.update(this.frame);
    this.version++;
  }

  onStatus(s: SimStatus): void {
    this.status = s;
  }

  get(id: string) {
    return this.byId.get(id);
  }

  ids(): ReadonlySet<string> {
    return new Set(this.byId.keys());
  }
}
