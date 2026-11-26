# PLAN — AudioConverter 2.0 (Tauri · React · FastAPI 전환)

CustomTkinter 앱을 jamak_converter와 같은 구조로 옮기는 계획입니다.
공통 구조의 기준 문서: [jamak_converter/docs/STRUCTURE.md](https://github.com/al8bright/jamak_converter/blob/main/docs/STRUCTURE.md)

- 작성: 2026-11-26
- 순서: video_converter 전환 다음에 합니다. 그쪽의 FFmpeg 실행기와 대기열(`Service`)을 가져다 씁니다.

---

## 목표

- 화면을 React로 다시 만들고, 변환 로직은 Python 백엔드로 옮깁니다.
- 변환 로직을 다시 씁니다. 지금은 진행률과 취소가 없고 테스트가 없습니다.
- FFmpeg를 설치 파일에 넣습니다.

## 하지 않는 것

- 태그 편집, 음량 맞추기, 새 형식 추가는 하지 않습니다.
- Mac 지원, video_converter와 합치기는 하지 않습니다.

---

## 지금 있는 기능 (그대로 유지)

README는 MP3 전용이라고 쓰여 있지만 코드는 아래까지 합니다. 이 표가 2.0의 기준입니다.

| 항목 | 내용 |
|---|---|
| 출력 형식 | MP3·M4A·OGG(비트레이트), FLAC·WAV(비트 깊이 16/24 + 샘플레이트) |
| 원본 분석 | ffprobe로 코덱, 비트레이트, 샘플레이트, 비트 깊이, 채널, DSD 여부 |
| 저장 위치 | 원본과 같은 폴더 / 지정 폴더 |
| 파일명 | 덮어쓰기 / 접미사 / 접두사 |
| 입력 | 파일·폴더 끌어다 놓기, 선택 창 |

### 변환할지 복사할지

"음질은 원본보다 높일 수 없다"는 규칙입니다. `should_encode`의 판단을 표로 옮긴 것입니다. 무손실끼리는 2.0에서 바꿨습니다(Phase 2 확인 뒤 결정).

| 원본 | 목표 | 동작 |
|---|---|---|
| DSD | 모든 형식 | 변환 |
| 무손실 | 손실 | 변환 |
| 무손실 | 무손실 | 목표가 원본보다 낮으면 변환. 같거나 높으면 형식이 같을 때 복사, 다를 때(WAV → FLAC 등) 원본 음질로 변환 |
| 손실 | 무손실 | 복사 |
| 손실 | 손실 | 목표 비트레이트가 원본보다 낮을 때만 변환, 아니면 복사. 원본 비트레이트를 모르면 변환 |

복사일 때 출력 경로가 원본과 같으면 건너뜁니다. 무손실로 만들 때 비트 깊이와 샘플레이트는 각각 원본보다 높이지 않습니다
(16bit/44.1k WAV를 FLAC 24bit/96k로 고르면 FLAC 16bit/44.1k). 1.x는 같은 음질의 WAV → FLAC을 복사해서 WAV를 FLAC으로 줄일 수 없었습니다.

---

## 고칠 것

| 문제 | 지금 | 2.0 |
|---|---|---|
| 진행률·취소 없음 | `subprocess.run`이 끝날 때까지 기다림 | video_converter의 실행기(진행률 해석, 중단, 프로세스 트리 종료, 멈춤 감지)를 씀 |
| 덮어쓰기 변환이 항상 실패 | 입력과 출력 경로가 같아 FFmpeg가 거부함 (`Output … same as Input`, 직접 실행해 확인. 원본은 손상되지 않음) | 임시 파일에 쓰고, 검증한 뒤 원본과 바꿈 |
| 한 번에 하나씩 | 순서대로 처리 | 대기열 구조를 같이 쓰므로 동시 변환이 가능. 기본값은 아래 "정할 것" |
| 테스트 없음 | — | 판단 표, 출력 경로, FFmpeg 명령을 테스트로 고정 |
| 실패 메시지 | FFmpeg 출력 전체 | 요약(시작 로그를 걸러 마지막 몇 줄) |
| `.spec` | `.gitignore`가 무시하는데 빌드 스크립트가 매번 다시 만듦 | `backend/packaging`에 두고 추적 |
| 복사가 형식을 바꾸려 함 (Phase 1에서 찾음) | 복사도 목표 확장자로 `-c:a copy`. MP3 → FLAC은 실패하고, FLAC → WAV는 FLAC 스트림이 든 `.wav`(플레이어가 못 엶) | 원본 파일을 형식·확장자 그대로 복사 |
| 앨범 그림 (Phase 1에서 찾음) | 그림이 있는 원본을 M4A로 만들면 실패. OGG는 그림이 Theora 영상 트랙이 됨 | MP3·M4A·FLAC은 그림을 다시 인코딩하지 않고 붙이고, OGG·WAV는 뺌. 태그는 모든 형식에 옮김 |
| 고음질 원본의 OGG (Phase 1에서 찾음) | 96kHz 원본이나 모노 22kHz + 320k는 libvorbis가 시작하지 못함 | 손실 형식은 48kHz를 넘지 않게 하고, 그래도 안 되면 품질 값(`-q:a`)으로 다시 만듦 |

---

## 구조

```
Tauri 창 (React) ──HTTP / WebSocket──▶ audioconverter-backend.exe ──▶ ffmpeg.exe / ffprobe.exe
```

### 백엔드 (`backend/src/audioconverter`)

| 파일 | 내용 |
|---|---|
| `core/probe.py` | 지금의 `get_audio_info`. 결과를 dict 대신 모델로 |
| `core/decide.py` | `is_lossless`, `should_encode`, 표시용 규격 문자열 |
| `core/ffmpeg_cmd.py` | 형식별 인코더 인자, 출력 경로(`resolve_output_path`) |
| `core/runner.py` | video_converter에서 가져옴 |
| `core/pipeline.py` | 분석 → 판단 → 변환 또는 복사 → 임시 파일 검증 → 교체 |
| `core/service.py` | video_converter에서 가져와 항목과 설정만 바꿈 |
| `core/proc.py`, `api/server.py`, `cli.py`, `config.py` | 공통 구조 |

### API

video_converter와 같은 경로를 씁니다: `/health`, `/system`, `/state`, `/events`, `/queue/paths`, `/queue/{id}`, `/queue/clear`, `/queue/clear-finished`, `/batch/start`, `/batch/stop`, `/settings`, `/open/file`, `/open/folder`.
설정 항목만 다릅니다: 출력 형식, 비트레이트 또는 비트 깊이·샘플레이트, 저장 위치, 파일명 규칙.

### 화면

| 화면 | 내용 |
|---|---|
| 대기열 | 끌어다 놓기, 목록(원본 규격 → 목표 규격, 예정 동작: 변환/복사/건너뜀, 상태), 진행 |
| 설정 | 출력 형식과 음질, 저장 위치, 파일명 규칙 |
| 하단 상태 줄 | FFmpeg 상태, 전체 진행 |

형식을 바꾸면 대기열의 "예정 동작"이 바로 다시 계산됩니다(지금도 그렇게 동작).

---

## 단계

### Phase 1 — 변환 로직 다시 쓰기

- [x] `backend/` 만들고 `core_converter.py`를 위 표대로 나눔 (공통 파일 `api/base.py`, `core/proc.py`, `tests/test_common.py`, `packaging/entry.py`, `scripts/`는 video_converter에서 복사)
- [x] 테스트: 판단 표 전체, 출력 경로, 형식별 FFmpeg 명령, 덮어쓰기(임시 파일 교체)
- [x] video_converter의 실행기로 진행률·중단. 강제 종료로 남은 임시 파일은 `core/leftovers.py`가 다음 시작 때 지움

완료 기준: `uv run pytest` 통과. CLI로 파일 하나를 형식별로 변환하고 덮어쓰기가 됩니다.

확인(2026-11-26): 테스트 93개 통과(FFmpeg가 PATH에 있으면 실제 변환 시험 포함, 없으면 그 시험만 건너뜀).
`uv run audioconverter convert`로 FLAC 24bit/96k(앨범 그림·한글 태그)를 MP3·M4A·OGG·FLAC 16/24bit·WAV로 변환해
ffprobe로 코덱·샘플레이트·비트 깊이·태그·그림을 확인했고, 10분짜리 파일에서 진행률이 나옴을 봤습니다.
덮어쓰기(같은 형식: 원본 교체, 다시 하면 건너뜀 / 다른 형식: 원본 남김), MP3 → FLAC·더 높은 비트레이트(복사),
모노 22kHz → OGG 320k(품질 값으로 다시)도 확인했습니다. 임시 파일은 남지 않았습니다.
`scripts/check_structure.py`: 지금 있는 공통 파일은 세 앱과 같음(화면·Tauri·빌드 파일은 Phase 2~5에서 생겨 아직 '없음').

남은 점: 복사한 파일의 이름에도 목표 규격 접미사(예: `_24bit_96k`)가 붙어 실제 규격과 다를 수 있습니다(1.x와 같음). → Phase 2에서 고침: 자동 이름은 결과의 실제 음질로 붙입니다.

### Phase 2 — Service와 API

- [x] `core/service.py`, `config.py`(설정 저장), `api/server.py`, `cli.py`(`serve`, `doctor`)
- [x] FFmpeg를 가짜로 바꾼 Service·API 테스트

설정: 출력 형식, 비트레이트(MP3·M4A·OGG), 비트 깊이·샘플레이트(FLAC·WAV), 동시 변환(비우면 권장값: 4개, 코어가 적으면 코어 수, 1~8),
저장 위치, 파일명 규칙(접미사·접두사·덮어쓰기)과 붙일 문구. 문구를 비우면 결과의 실제 음질로 붙입니다
(변환 `_192k`, 복사는 원본 음질 `_16bit_44.1k`, 접두사 `[192k]_`). 1.x는 복사한 파일에도 목표 음질을 붙였습니다.
대기열 항목은 예정 동작(`encode` · `copy` · `skip`), 만들 파일 이름, 덮어쓰기인데 형식이 달라 원본이 남는지(`keeps_source`)를 함께 보냅니다.

확인(2026-11-26): 테스트 134개 통과. `doctor`는 ffmpeg·ffprobe와 인코더(libmp3lame·aac·libvorbis·flac)를 확인합니다.
`serve`를 띄워 HTTP로 폴더(6개)를 담고 FLAC 16bit/44.1k로 동시 4개 변환(변환 2 · 복사 4)했고,
10분짜리 3개를 변환하다 `/batch/stop`으로 멈춰 ffmpeg가 모두 끝나고 임시 파일이 남지 않음을 확인했습니다.

결정(2026-11-26): 무손실끼리 음질이 같거나 목표가 높아도 형식이 다르면 원본 음질 그대로 변환합니다(위 표에 반영).
WAV 16bit/44.1k(1.4MB)를 FLAC 24bit/96k로 골라 FLAC 16bit/44.1k(107KB)가 되는 것을 확인했습니다. 테스트 138개 통과.

### Phase 3 — 화면

- [x] 공통 파일을 넣고 대기열·설정 화면 (video_converter의 `app/`에서 시작해 항목·설정·문구를 바꿈)
- [x] `DESIGN.md`

화면: 대기열(원본 음질 · 할 일 변환/복사/건너뜀 · 만들 파일 이름 · 덮어쓰기로 원본이 남으면 '원본 남김'), 설정(출력 형식, 비트레이트,
비트 깊이·샘플레이트 — 형식에 맞지 않는 칸은 잠금, 동시 변환, 저장 위치, 파일 이름: 접미사·접두사·덮어쓰기와 문구, 비우면 자동),
도움말(변환 규칙, 태그·앨범 그림, 안전한 저장). 덮어쓰기로 시작하면 바뀔 원본 수와 남을 원본 수를 묻습니다.

확인(2026-11-26): `pnpm lint`(video와 같은 경고 4개뿐) · `pnpm build` 통과. 브라우저(Orca)에서 백엔드에 폴더(7개, 망가진 파일 1개 포함)를 담아
대기열 표시를 보고, '변환 시작'으로 동시 4개 변환(변환 4 · 복사 2, 망가진 파일은 고를 수 없음)과 진행 카드, 설정 화면(FLAC · 접두사)을 확인했습니다.
끌어다 놓기와 파일·폴더 선택 창은 Phase 4(Tauri)에서 봅니다.

### Phase 4 — Tauri 셸

- [ ] 공통 `lib.rs`, 끌어다 놓기, 닫기 확인, 아이콘(`audio_icon.png`에서 다시 만듦)

### Phase 5 — 설치 파일, CI, 문서

- [ ] `scripts/build_app.ps1`(정해 둔 FFmpeg 빌드), `THIRD_PARTY_NOTICES.md`, `LICENSE`(MIT), CI
- [ ] README를 실제 기능에 맞게 다시 씀

### Phase 6 — 옛 화면 제거, 2.0.0

- [ ] `gui_app.py`, `core_converter.py`, `requirements.txt`, `run_app.bat`, `build_exe.bat` 삭제

---

## 확인할 것 (실제 파일)

- 형식 5종 각각의 변환과 복사, DSD 원본
- 24bit/96kHz FLAC → 16bit/44.1kHz, 그 반대(복사가 되어야 함)
- 덮어쓰기: 같은 형식, 다른 형식(확장자가 바뀌면 원본이 남는 것이 맞는지 포함)
- 태그와 앨범 그림이 변환 뒤에도 남는지. 지금 명령은 따로 지정하지 않아 FFmpeg 기본 동작에 맡기고 있어, 형식 조합별로 확인이 필요합니다
- 수백 개 넣었을 때 목록과 진행 표시

## 정할 것

| | 내용 | 제안 |
|---|---|---|
| 동시 변환 | 지금은 하나씩. 오디오 인코딩은 CPU 작업 | 기본 4개(코어 수 안에서), 설정에서 변경 |
| 덮어쓰기 + 다른 형식 | `a.flac`을 MP3로 "덮어쓰기"하면 `a.mp3`가 생기고 `a.flac`은 남음 | 지금 동작 유지하고 화면에 그렇게 표시 |
| FFmpeg 빌드 | 필요한 인코더(libmp3lame, libvorbis, flac, aac)는 LGPL 빌드에도 있음 | video_converter와 같은 빌드를 써서 빌드 스크립트를 같게 둠 |
