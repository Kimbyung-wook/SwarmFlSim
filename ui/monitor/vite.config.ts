// IMP-MON-012: Vite 설정. 외부 자산 없이 로컬에서 제공한다 (DEC-003). GCS/UI(5173)와 다른 포트를 쓴다
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
  preview: { port: 4174 },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
