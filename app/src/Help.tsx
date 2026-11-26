import { useApp } from "./ctx";
import { eyebrow, Page } from "./ui";

export function HelpScreen() {
  const { system } = useApp();
  const exts = system?.extensions.join(" ") ?? ".mp3 .m4a .ogg .flac .wav .ape .dsf .dff";
  return (
    <Page title="도움말" eyebrow={eyebrow("HELP", "변환 규칙과 팁")}>
      <section className="card help">
        <h2>변환할지 복사할지</h2>
        <p>음질은 원본보다 높일 수 없다는 규칙으로 정합니다. 대기열의 '할 일'이 지금 설정으로 무엇을 할지 보여 줍니다.</p>
        <ul>
          <li>DSD 원본은 늘 변환합니다.</li>
          <li>무손실(FLAC · WAV · APE 등) 원본을 MP3 · M4A · OGG로 고르면 변환합니다.</li>
          <li>
            무손실 원본을 FLAC · WAV로 고르면, 목표가 원본보다 낮을 때 낮춰서 변환합니다. 같거나 높으면 형식이 같을 때는 복사하고,
            다를 때는(WAV → FLAC 등) 원본 음질 그대로 변환합니다.
          </li>
          <li>MP3 · M4A · OGG 원본은 목표 비트레이트가 원본보다 낮을 때만 변환하고, 아니면 복사합니다. FLAC · WAV로 바꿔도 음질이 오르지 않아 복사합니다.</li>
          <li>복사는 원본 파일을 형식 그대로 둡니다. 복사할 곳이 원본 자리(덮어쓰기)면 건너뜁니다.</li>
        </ul>
      </section>

      <section className="card help">
        <h2>태그와 앨범 그림</h2>
        <ul>
          <li>제목 · 아티스트 · 앨범 같은 태그는 모든 형식에 옮깁니다.</li>
          <li>앨범 그림은 MP3 · M4A · FLAC에 다시 인코딩하지 않고 넣습니다. OGG와 WAV에는 넣지 않습니다.</li>
          <li>MP3 · M4A · OGG는 48kHz를 넘는 샘플레이트로 만들지 않습니다. 사람이 듣는 범위에서 차이가 없습니다.</li>
        </ul>
      </section>

      <section className="card help">
        <h2>안전한 저장과 실패할 때</h2>
        <ul>
          <li>결과는 임시 파일에 먼저 쓰고, 다 만든 뒤 확인한 다음에 제 이름으로 바꿉니다. 덮어쓰기도 이 뒤에만 원본을 바꿉니다.</li>
          <li>중단하거나 앱이 강제로 끝나도 만들다 만 파일은 남지 않습니다(강제 종료 때는 다음 실행 때 지웁니다).</li>
          <li>5분 동안 진행이 없으면 멈춘 것으로 보고 끝냅니다.</li>
          <li>실패한 파일은 대기열에서 사유를 확인할 수 있고, '변환 시작'을 다시 누르면 다시 변환합니다.</li>
          <li>FFmpeg가 남긴 자세한 오류는 <span className="mono">%APPDATA%\AudioConverter\conversion_errors.log</span>에 쌓입니다.</li>
        </ul>
      </section>

      <section className="card help">
        <h2>넣을 수 있는 파일</h2>
        <p className="mono">{exts}</p>
        <p>폴더를 넣으면 하위 폴더까지 찾아 위 형식의 파일만 담습니다. 같은 파일은 한 번만 담깁니다.</p>
      </section>
    </Page>
  );
}
