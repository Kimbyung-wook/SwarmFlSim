// IMP-MON-008: 고정 용량 원형 버퍼. 타임라인(LinkOutcome)과 메시지 echo(LinkEnvelope)가 쓴다 (REQ-UI-005)
// 부하가 커도 메모리가 늘지 않도록 오래된 항목을 덮어쓴다.
export class Ring<T> {
  private readonly buf: (T | undefined)[];
  private head = 0; // 다음 쓸 위치
  private n = 0;
  /** 지금까지 넣은 총 개수 */
  pushed = 0;

  constructor(readonly capacity: number) {
    this.buf = new Array<T | undefined>(capacity);
  }

  get size(): number {
    return this.n;
  }

  /** 밀려난 항목을 돌려준다 */
  push(v: T): T | undefined {
    const old = this.n === this.capacity ? this.buf[this.head] : undefined;
    this.buf[this.head] = v;
    this.head = (this.head + 1) % this.capacity;
    if (this.n < this.capacity) this.n++;
    this.pushed++;
    return old;
  }

  /** 최신부터 거꾸로. fn이 false를 돌려주면 멈춘다 */
  forEachNewest(fn: (v: T) => boolean | void): void {
    for (let i = 0; i < this.n; i++) {
      const v = this.buf[(this.head - 1 - i + this.capacity) % this.capacity] as T;
      if (fn(v) === false) return;
    }
  }

  /** 최신부터 조건에 맞는 것을 최대 limit개 */
  newest(limit: number, pred: (v: T) => boolean = () => true): T[] {
    const out: T[] = [];
    this.forEachNewest((v) => {
      if (pred(v)) out.push(v);
      return out.length < limit;
    });
    return out;
  }

  clear(): void {
    this.buf.fill(undefined);
    this.head = 0;
    this.n = 0;
  }
}
