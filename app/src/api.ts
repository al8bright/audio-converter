// 백엔드 클라이언트: 연결은 공통 파일 `backend.ts` 가 맡고, 여기서는 이벤트와 응답 형태를 둔다.

import { socket } from "./backend";

export { ApiError, api, connect, inTauri } from "./backend";

/** 상태 변경을 받는다. 끊기면 1초 뒤 다시 붙는다. 돌려준 함수로 닫는다. */
export function events(handlers: { state: (s: AppData) => void; link: (up: boolean) => void }): () => void {
  return socket("/events", (data) => {
    const e = data as { type: string };
    if (e.type === "state") handlers.state(e as unknown as AppData);
  }, handlers.link);
}

// ---------------------------------------------------------------------- 형태 (core/service.py, config.py)

export type Status = "analyzing" | "waiting" | "converting" | "done" | "copied" | "skipped" | "failed" | "stopped";
export type Format = "MP3" | "M4A" | "OGG" | "FLAC" | "WAV";
export type Bitrate = 320 | 256 | 192 | 128;
export type BitDepth = 24 | 16;
export type SampleRate = 192000 | 96000 | 48000 | 44100;
export type NameMode = "suffix" | "prefix" | "overwrite";

/** 지금 설정으로 변환하면 할 일. 오디오 정보를 못 읽었으면 null */
export interface Plan {
  action: "encode" | "copy" | "skip"; // 변환 | 원본 그대로 복사 | 복사할 곳이 원본 자리라 둠
  output: string; // 만들 파일 이름
  keeps_source: boolean; // 덮어쓰기인데 형식이 달라 원본이 남는다
}

/** ffprobe 로 읽은 원본(core/probe.py 의 AudioInfo) */
export interface AudioInfo {
  codec: string;
  sample_rate: number;
  bit_rate: number;
  bit_depth: number;
  channels: number;
  duration: number;
  has_cover: boolean;
  dsd: string;
  lossless: boolean;
  label: string;
}

export interface Item {
  id: string;
  path: string;
  name: string;
  size: number;
  info: AudioInfo | null;
  source: string; // 원본 음질: FLAC 24bit/96k
  duration: number;
  status: Status;
  message: string | null;
  output: string | null;
  percent: number;
  time: string;
  speed: string;
  plan: Plan | null;
}

export interface BatchResult {
  message: string;
  all_ok: boolean;
  done: number;
  copied: number;
  skipped: number;
  failed: number;
  stopped: number;
  total: number;
}

export interface Batch {
  running: boolean;
  stop_requested: boolean;
  total: number;
  finished: number;
  jobs: number;
  started_at: number | null;
  result: BatchResult | null;
  added_during: number;
  overall: number;
}

export interface Settings {
  jobs: number | null; // null 이면 권장값
  format: Format;
  bitrate: Bitrate; // MP3·M4A·OGG
  bit_depth: BitDepth; // FLAC·WAV
  sample_rate: SampleRate; // FLAC·WAV
  save_mode: "same" | "folder";
  save_dir: string;
  name_mode: NameMode;
  name_text: string; // 비우면 결과의 음질로 자동
  sidebar: "open" | "closed";
}

export interface Notice {
  id: number;
  text: string;
  tone: "info" | "warn";
}

export interface AppData {
  version: number;
  items: Item[];
  batch: Batch;
  settings: Settings;
  target: string; // 목표 음질: MP3 192k
  notices: Notice[];
}

export interface SystemInfo {
  version: string;
  ffmpeg: string | null;
  ffprobe: string | null;
  extensions: string[];
  max_jobs: number;
  formats: Format[];
  bitrates: Bitrate[];
  bit_depths: BitDepth[];
  sample_rates: SampleRate[];
  cpu_count: number;
  recommended_jobs: number;
}

/** 응답에 사용자에게 보여 줄 안내가 실려 오는 동작들 */
export interface WithMessage {
  message?: string | null;
}
