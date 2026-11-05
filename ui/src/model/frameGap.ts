// IMP-UI-059: 재생 중 truth/state 프레임 번호 공백으로 누락 프레임을 센다 (DEC-042, REQ-UI-001)
// 재생기는 배속·역압이 없어 빠르게 돌리면 버스·브리지에서 프레임이 빠진다. 재생기 동작은 바꾸지 않고 세기만 한다.
import { fromBinary } from "@bufbuild/protobuf";
import { HeaderSchema } from "../gen/swarm/v1/common_pb";

/** TruthFrame의 header(필드 1)만 해석해 프레임 번호를 꺼낸다. 엔티티 전체를 해석하지 않으려는 것이다 */
export function peekFrameNumber(payload: Uint8Array): bigint | null {
  if (payload.length < 2 || payload[0] !== 0x0a) return null;
  let len = 0;
  let shift = 0;
  let i = 1;
  for (; i < payload.length && i < 6; i++) {
    const b = payload[i];
    len |= (b & 0x7f) << shift;
    shift += 7;
    if ((b & 0x80) === 0) {
      i++;
      break;
    }
  }
  if (i + len > payload.length) return null;
  try {
    return fromBinary(HeaderSchema, payload.subarray(i, i + len)).frame;
  } catch {
    return null;
  }
}

export class FrameGapCounter {
  /** 이번 재생에서 빠진 프레임 수 */
  missed = 0;
  private last: bigint | null = null;
  private inReplay = false;

  /** 재생이 아니면 세지 않고 이전 값도 잊는다. 재생이 새로 시작하거나 프레임 번호가 거꾸로 가면 0부터 다시 센다 */
  feed(frame: bigint, replay: boolean): void {
    if (!replay) {
      this.inReplay = false;
      this.last = null;
      return;
    }
    if (!this.inReplay) {
      this.inReplay = true;
      this.missed = 0;
      this.last = null;
    }
    if (this.last !== null) {
      if (frame < this.last) this.missed = 0;
      else if (frame > this.last + 1n) this.missed += Number(frame - this.last - 1n);
    }
    this.last = frame;
  }
}

/** DEC-041: 응답하지 않는 참여자 이름 목록을 경고 문구로 만든다. 비면 null */
export function waitingWarning(names: readonly string[] | undefined): string | null {
  if (!names || names.length === 0) return null;
  return `참여자 응답 없음: ${names.join(", ")} — Reset 후 Start로 복구`;
}
