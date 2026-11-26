/** 앱마다 다른 값. 공통 파일(backend.ts, vite.config.ts)이 이름과 포트를 여기서 읽는다. (docs/STRUCTURE.md) */

export const NAME = "audioconverter"; // 토큰 헤더 x-audioconverter-token
export const DEV_BACKEND_PORT = 8768; // `audioconverter serve` 기본 포트(브라우저로 개발할 때)
export const VITE_PORT = 5176; // pnpm dev. tauri.conf.json의 devUrl과 같아야 한다
