// 화면에 보이는 문구와 숫자 모양. 백엔드는 코드 값만 보내고, 문구는 여기서 정한다.

import type { BitDepth, Bitrate, Format, Item, Plan, SampleRate, Settings, Status } from "./api";

export const FORMATS: Format[] = ["MP3", "M4A", "OGG", "FLAC", "WAV"];
export const LOSSLESS: Format[] = ["FLAC", "WAV"];
export const BITRATES: Bitrate[] = [320, 256, 192, 128];
export const BIT_DEPTHS: BitDepth[] = [24, 16];
export const SAMPLE_RATES: SampleRate[] = [192000, 96000, 48000, 44100];

export const FORMAT_HINT: Record<Format, string> = {
  MP3: "어디서나 재생됩니다",
  M4A: "AAC. 같은 비트레이트면 MP3보다 음질이 낫습니다",
  OGG: "Vorbis. 앨범 그림은 넣지 않습니다",
  FLAC: "무손실 압축. 태그와 앨범 그림을 담습니다",
  WAV: "무손실, 압축하지 않음. 파일이 큽니다",
};

export const isLossless = (f: Format) => LOSSLESS.includes(f);

/** 44100 → 44.1, 96000 → 96 */
export const khz = (rate: number) => String(rate / 1000);

/** 지금 설정의 목표 음질: MP3 192k, FLAC 24bit/96k */
export function targetLabel(s: Settings): string {
  return isLossless(s.format) ? `${s.format} ${s.bit_depth}bit/${khz(s.sample_rate)}k` : `${s.format} ${s.bitrate}k`;
}

/** 자동 이름에 붙는 문구(백엔드 decide.auto_value 와 같은 규칙). 문구를 적었으면 그것 */
export function nameValue(s: Settings): string {
  if (s.name_mode === "overwrite") return "";
  if (s.name_text) return s.name_text;
  const affix = isLossless(s.format) ? `${s.bit_depth}bit_${khz(s.sample_rate)}k` : `${s.bitrate}k`;
  return s.name_mode === "suffix" ? `_${affix}` : `[${affix}]_`;
}

const EXT: Record<Format, string> = { MP3: ".mp3", M4A: ".m4a", OGG: ".ogg", FLAC: ".flac", WAV: ".wav" };

/** 저장될 이름의 예: song.flac → song_192k.mp3 */
export function exampleName(s: Settings): string {
  const v = nameValue(s);
  const name = s.name_mode === "prefix" ? `${v}song` : `song${v}`;
  return `song.flac → ${name}${EXT[s.format]}`;
}

export function fmtBytes(n: number): string {
  if (!n) return "-";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** 초 → 1:02:03 또는 2:03. 모르면 "-". */
export function fmtDuration(sec: number): string {
  if (!sec || sec < 0) return "-";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** ffmpeg time=00:01:02.34 → 1:02 */
export function fmtClock(t: string): string {
  const m = /^(\d+):(\d+):(\d+)/.exec(t);
  return m ? fmtDuration(Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3])) : "-";
}

/** 파일이 있는 폴더(전체 경로에서 파일 이름을 뺀 것) */
export function folderOf(path: string): string {
  const i = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return i > 0 ? path.slice(0, i) : path;
}

export const baseName = (path: string) => path.slice(folderOf(path).length + 1);

export const PLAN_LABEL: Record<Plan["action"], { label: string; hint: string }> = {
  encode: { label: "변환", hint: "목표 형식과 음질로 다시 인코딩합니다. 원본보다 음질을 높이지는 않습니다" },
  copy: { label: "복사", hint: "원본 음질이 목표보다 낮거나 같아 원본 파일을 형식 그대로 복사합니다" },
  skip: { label: "건너뜀", hint: "복사할 곳이 원본 자리라 그대로 둡니다" },
};

export const STARTABLE: Status[] = ["waiting", "stopped", "failed"];
/** 정보를 못 읽어 실패한 파일은 다시 해도 같아 고를 수 없다 */
export const isStartable = (i: Item) => STARTABLE.includes(i.status) && !!i.info;

/** 상태 배지: 문구, 색(tone), 배지 밑에 적을 사유 */
export function describeStatus(i: Item): { label: string; tone: string; reason?: string } {
  switch (i.status) {
    case "analyzing": return { label: "분석 중", tone: "busy" };
    case "waiting": return { label: "대기", tone: "waiting" };
    case "converting": return { label: `변환 중 ${Math.round(i.percent * 100)}%`, tone: "converting" };
    case "done": return { label: "완료", tone: "ok", reason: noteOf(i.message) };
    case "copied": return { label: "복사함", tone: "ok" };
    case "skipped": return { label: "건너뜀", tone: "waiting" };
    case "failed": return { label: "실패", tone: "err", reason: i.message ?? undefined };
    case "stopped": return { label: "중단", tone: "stopped" };
  }
}

/** 완료 문구 끝의 괄호 안내만 사유로 보인다: "… → MP3 192k (형식이 달라 원본은 그대로 둠)" */
function noteOf(message: string | null): string | undefined {
  const m = message ? /\(([^)]+)\)\s*$/.exec(message) : null;
  return m ? m[1] : undefined;
}

export const FILTERS = ["전체", "대기", "진행", "완료", "실패"] as const;
export type Filter = (typeof FILTERS)[number];

export function bucketOf(i: Item): Filter {
  if (i.status === "converting") return "진행";
  if (i.status === "done" || i.status === "copied" || i.status === "skipped") return "완료";
  if (i.status === "failed") return "실패";
  return "대기";
}

export function countBuckets(items: Item[]): Record<Filter, number> {
  const c: Record<Filter, number> = { 전체: items.length, 대기: 0, 진행: 0, 완료: 0, 실패: 0 };
  for (const i of items) c[bucketOf(i)] += 1;
  return c;
}

export function describeSummary(items: Item[]): string {
  if (!items.length) return "비어 있음";
  const c = countBuckets(items);
  const parts = [`${items.length}개`];
  if (c.대기) parts.push(`대기 ${c.대기}`);
  if (c.완료) parts.push(`완료 ${c.완료}`);
  if (c.실패) parts.push(`실패 ${c.실패}`);
  return parts.join(" · ");
}

/** 변환을 시작하기 전에 받아야 할 확인. 없으면 빈 배열. picked 는 변환할 항목. */
export function startWarnings(s: Settings, picked: Item[]): string[] {
  if (s.name_mode !== "overwrite") return [];
  const replaced = picked.filter((i) => i.plan?.action === "encode" && !i.plan.keeps_source).length;
  const kept = picked.filter((i) => i.plan?.keeps_source).length;
  const out: string[] = [];
  if (replaced) {
    out.push(s.save_mode === "same"
      ? `원본 ${replaced}개를 변환한 파일로 바꿉니다. 다 만들고 확인한 뒤에 바꾸지만, 바뀐 원본은 되돌릴 수 없습니다.`
      : `저장 폴더에 같은 이름의 파일이 있으면 그 파일이 바뀝니다(${replaced}개).`);
  }
  if (kept) out.push(`${kept}개는 형식이 달라 원본은 그대로 두고 새 파일을 만듭니다.`);
  return out;
}

/** 이미 떠 있는 알림에 새 알림을 덧붙인다(같은 문구는 한 번만). */
export function mergeMessages(existing: string, next: string): string {
  const a = existing.trim();
  const b = next.trim();
  if (!a) return b;
  if (!b || a.includes(b)) return a;
  return `${a}\n\n${"-".repeat(20)}\n\n${b}`;
}
