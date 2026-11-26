import { useState } from "react";
import { api, inTauri, type Settings } from "./api";
import { useApp } from "./ctx";
import { BIT_DEPTHS, BITRATES, exampleName, FORMAT_HINT, FORMATS, isLossless, khz, nameValue, SAMPLE_RATES } from "./format";
import { ICONS } from "./icons";
import { eyebrow, Icon, Note, Page, Seg } from "./ui";

export function SettingsScreen() {
  const { data, system, act } = useApp();
  const s = data.settings;
  const locked = data.batch.running;
  const lossless = isLossless(s.format);
  const put = (patch: Partial<Settings>) => act(() => api.put("/settings", patch));

  const [dirDraft, setDirDraft] = useState<string | null>(null);
  const [textDraft, setTextDraft] = useState<string | null>(null);
  const dir = dirDraft ?? s.save_dir;
  const text = textDraft ?? s.name_text;
  const commitDir = async (value: string) => {
    if (value.trim() && value !== s.save_dir) await put({ save_dir: value });
    setDirDraft(null);
  };
  const commitText = async () => {
    if (text !== s.name_text) await put({ name_text: text.trim() });
    setTextDraft(null);
  };
  const browse = async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const picked = await open({ directory: true, defaultPath: s.save_dir || undefined, title: "저장 폴더 고르기" });
    if (typeof picked === "string") {
      await commitDir(picked);
      if (s.save_mode !== "folder") await put({ save_mode: "folder" });
    }
  };

  const recommended = system?.recommended_jobs;
  const jobOptions = [
    { value: 0, label: recommended ? `권장 ${recommended}` : "권장" },
    ...Array.from({ length: system?.max_jobs ?? 8 }, (_, i) => ({ value: i + 1, label: String(i + 1) })),
  ];
  // 문구 칸을 비우면 쓰일 자동 문구(지금 형식·음질 기준)
  const autoText = nameValue({ ...s, name_text: "" });

  return (
    <Page title="설정" eyebrow={eyebrow("SETTINGS", locked ? "변환하는 동안 잠김" : "바꾸면 바로 저장됩니다")}>
      {locked && <Note tone="warn">변환하는 동안은 설정을 바꿀 수 없습니다. 끝나거나 중단한 뒤 바꿔 주세요.</Note>}

      <section className="card" aria-label="출력 형식과 음질">
        <h2>출력 형식과 음질</h2>
        <div className="setting">
          출력 형식
          <Seg label="출력 형식" value={s.format} disabled={locked}
            options={FORMATS.map((f) => ({ value: f, label: f }))} onChange={(v) => put({ format: v })} />
          <span className="hint">{FORMAT_HINT[s.format]}</span>
        </div>
        <div className="setting">
          비트레이트 (MP3 · M4A · OGG)
          <Seg label="비트레이트" value={s.bitrate} disabled={locked || lossless}
            options={BITRATES.map((v) => ({ value: v, label: `${v}k` }))} onChange={(v) => put({ bitrate: v })} />
          <span className="hint">
            원본 비트레이트가 이보다 낮거나 같으면 다시 인코딩하지 않고 원본을 복사합니다. 무손실 원본은 늘 변환합니다.
          </span>
        </div>
        <div className="setting">
          비트 깊이 · 샘플레이트 (FLAC · WAV)
          <div className="seg-row">
            <Seg label="비트 깊이" value={s.bit_depth} disabled={locked || !lossless}
              options={BIT_DEPTHS.map((v) => ({ value: v, label: `${v}bit` }))} onChange={(v) => put({ bit_depth: v })} />
            <Seg label="샘플레이트" value={s.sample_rate} disabled={locked || !lossless}
              options={SAMPLE_RATES.map((v) => ({ value: v, label: `${khz(v)}kHz` }))} onChange={(v) => put({ sample_rate: v })} />
          </div>
          <span className="hint">
            원본보다 높이지 않습니다. 16bit/44.1kHz 원본을 24bit/96kHz로 고르면 16bit/44.1kHz로 만듭니다.
            손실 형식(MP3 등) 원본은 무손실로 바꿔도 음질이 오르지 않아 원본을 복사합니다.
          </span>
        </div>
      </section>

      <section className="card" aria-label="동시 변환">
        <h2>동시 변환</h2>
        <div className="setting">
          한 번에 변환할 파일 수
          <Seg label="동시 변환 작업 수" value={s.jobs ?? 0} disabled={locked} options={jobOptions}
            onChange={(v) => put({ jobs: v === 0 ? null : v })} />
          <span className="hint">
            파일 하나에 CPU 코어 하나쯤을 씁니다. 권장값은 4개이고, 코어가 그보다 적으면 코어 수입니다
            {system ? `(이 PC: ${system.cpu_count}코어)` : ""}.
          </span>
        </div>
      </section>

      <section className="card" aria-label="저장">
        <h2>저장</h2>
        <div className="setting">
          저장 위치
          <Seg label="저장 위치" value={s.save_mode} disabled={locked}
            options={[{ value: "same", label: "원본과 같은 폴더" }, { value: "folder", label: "지정 폴더" }]}
            onChange={(v) => put({ save_mode: v })} />
          <div className="path-row">
            <input className="field path" value={dir} disabled={locked || s.save_mode !== "folder"} aria-label="저장 폴더"
              spellCheck={false} placeholder="저장할 폴더 경로" onChange={(e) => setDirDraft(e.target.value)}
              onBlur={() => commitDir(dir)} onKeyDown={(e) => e.key === "Enter" && commitDir(dir)} />
            {inTauri && <button className="btn" disabled={locked} onClick={browse}>변경</button>}
            <button className="btn cyan-ghost" disabled={s.save_mode !== "folder" || !s.save_dir}
              onClick={() => act(() => api.post("/open/folder", {}))}><Icon d={ICONS.open} size={13} /> 열기</button>
          </div>
        </div>
        <div className="setting">
          파일 이름
          <Seg label="파일 이름" value={s.name_mode} disabled={locked}
            options={[{ value: "suffix", label: "접미사 붙이기" }, { value: "prefix", label: "접두사 붙이기" },
              { value: "overwrite", label: "같은 이름 (덮어쓰기)" }]}
            onChange={(v) => put({ name_mode: v })} />
          {s.name_mode !== "overwrite" && (
            <input className="field suffix" value={text} disabled={locked} spellCheck={false}
              aria-label={s.name_mode === "suffix" ? "접미사" : "접두사"} placeholder={`자동: ${autoText}`}
              onChange={(e) => setTextDraft(e.target.value)} onBlur={commitText}
              onKeyDown={(e) => e.key === "Enter" && commitText()} />
          )}
          <span className="hint mono">{exampleName(s)}</span>
          {s.name_mode !== "overwrite" && !s.name_text && (
            <span className="hint">비워 두면 결과의 실제 음질을 붙입니다. 원본을 복사한 파일에는 원본 음질이 붙습니다.</span>
          )}
          {s.name_mode === "overwrite" && (
            <Note tone="warn">
              {s.save_mode === "same"
                ? "형식이 같으면 원본을 변환한 파일로 바꿉니다(다 만들고 확인한 뒤). 형식이 다르면 원본은 그대로 두고 새 파일을 만듭니다."
                : "저장 폴더에 같은 이름의 파일이 있으면 바뀝니다."}
            </Note>
          )}
        </div>
      </section>
    </Page>
  );
}
