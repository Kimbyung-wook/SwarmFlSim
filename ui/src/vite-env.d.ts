/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_IMAGERY_URL?: string;
  readonly VITE_TERRAIN_URL?: string;
  /** 브리지 주소 (기본 ws://<페이지 호스트>:8765/bus) */
  readonly VITE_BRIDGE_URL?: string;
  /** 이 UI가 맡은 GCS 엔티티 (기본 gcs-01) */
  readonly VITE_GCS?: string;
}
