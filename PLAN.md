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

"음질은 원본보다 높일 수 없다"는 규칙입니다. `should_encode`의 판단을 표로 옮긴 것이고, 2.0에서도 같아야 합니다.

| 원본 | 목표 | 동작 |
|---|---|---|
| DSD | 모든 형식 | 변환 |
| 무손실 | 손실 | 변환 |
| 무손실 | 무손실 | 목표(비트 깊이 × 샘플레이트)가 원본보다 낮을 때만 변환, 아니면 복사 |
| 손실 | 무손실 | 복사 |
| 손실 | 손실 | 목표 비트레이트가 원본보다 낮을 때만 변환, 아니면 복사. 원본 비트레이트를 모르면 변환 |

복사일 때 출력 경로가 원본과 같으면 건너뜁니다.

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

- [ ] `backend/` 만들고 `core_converter.py`를 위 표대로 나눔
- [ ] 테스트: 판단 표 전체, 출력 경로, 형식별 FFmpeg 명령, 덮어쓰기(임시 파일 교체)
- [ ] video_converter의 실행기로 진행률·중단

완료 기준: `uv run pytest` 통과. CLI로 파일 하나를 형식별로 변환하고 덮어쓰기가 됩니다.

### Phase 2 — Service와 API

- [ ] `core/service.py`, `config.py`(설정 저장), `api/server.py`, `cli.py`(`serve`, `doctor`)
- [ ] FFmpeg를 가짜로 바꾼 Service·API 테스트

### Phase 3 — 화면

- [ ] 공통 파일을 넣고 대기열·설정 화면
- [ ] `DESIGN.md`

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
