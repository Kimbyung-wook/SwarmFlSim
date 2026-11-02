// IMP-MON-001: proto/swarm/v1 → src/gen (protobuf-es). REQ-UI-005, DEC-003
// buf CLI와 protoc-gen-es는 node_modules에서 찾는다. 외부 서비스에 접속하지 않는다.
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const monDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const bin = join(monDir, "node_modules", ".bin");
const sep = process.platform === "win32" ? ";" : ":";
const env = { ...process.env, PATH: `${bin}${sep}${process.env.PATH ?? ""}` };

const buf = join(monDir, "node_modules", "@bufbuild", "buf", "bin", "buf");
const r = spawnSync(process.execPath, [buf, "generate", "--template", "buf.gen.yaml"], {
  cwd: monDir,
  env,
  stdio: "inherit",
});
if (r.status !== 0) {
  console.error("gen-proto: buf generate 실패");
  process.exit(r.status ?? 1);
}
console.log("gen-proto: src/gen 생성 완료");
