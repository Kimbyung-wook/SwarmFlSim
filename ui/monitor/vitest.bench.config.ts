// TC-MON-009: 부하 측정 전용 설정 (npm run bench). 일반 시험(npm test)에는 넣지 않는다
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.load.ts"],
    testTimeout: 120_000,
  },
});
