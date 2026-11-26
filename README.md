# 🎵 Audio Converter

음악 파일을 MP3 · M4A · OGG · FLAC · WAV로 한꺼번에 바꾸는 Windows 데스크톱 앱입니다.
**음질은 원본보다 높일 수 없다**는 규칙으로 파일마다 변환할지 원본을 복사할지 정하고, 변환 전에 대기열에서 보여 줍니다.

> 2.0에서 화면을 CustomTkinter에서 React + Tauri로 바꾸고 변환 로직을 다시 썼으며, FFmpeg를 설치 파일에 넣었습니다([PLAN.md](PLAN.md)).

---

## ✨ 주요 기능

- **다섯 가지 출력 형식**: MP3 · M4A(AAC) · OGG(Vorbis)는 비트레이트(320 · 256 · 192 · 128k), FLAC · WAV는 비트 깊이(24 · 16bit)와 샘플레이트(192 · 96 · 48 · 44.1kHz)로 고릅니다.
- **원본보다 높이지 않음**: 원본 비트레이트가 목표보다 낮거나 같은 MP3 등은 다시 인코딩하지 않고 원본을 그대로 복사합니다. 무손실로 만들 때도 비트 깊이 · 샘플레이트를 원본보다 높이지 않습니다. 규칙은 [아래 표](#변환할지-복사할지)에 있습니다.
- **할 일 미리 보기**: 대기열에서 파일마다 원본 음질과 '변환 · 복사 · 건너뜀', 만들 파일 이름을 변환 전에 보여 줍니다. 설정을 바꾸면 바로 다시 계산합니다.
- **동시 변환**: 기본 4개(CPU 코어가 적으면 코어 수), 1~8개로 바꿀 수 있습니다. 파일마다 진행률과 배속을 보여 주고 언제든 중단할 수 있습니다.
- **태그와 앨범 그림**: 태그는 모든 형식에 옮기고, 앨범 그림은 MP3 · M4A · FLAC에 다시 인코딩하지 않고 넣습니다.
- **끌어다 놓기와 폴더 검색**: 파일이나 폴더를 창에 끌어다 놓으면 하위 폴더까지 찾아 담습니다.
- **안전한 저장**: 결과는 임시 파일에 먼저 쓰고, 다 만든 뒤 확인한 다음에 제 이름으로 바꿉니다. 덮어쓰기도 이 뒤에만 원본을 바꿉니다.
  중단하거나 앱이 강제로 끝나도 만들다 만 파일은 남지 않습니다(강제 종료 때는 다음 실행 때 지움).

넣을 수 있는 파일: `.mp3`, `.m4a`, `.ogg`, `.flac`, `.wav`, `.ape`, `.dsf`, `.dff`

### 변환할지 복사할지

| 원본 | 목표 | 동작 |
| --- | --- | --- |
| DSD | 모든 형식 | 변환 |
| 무손실 (FLAC · WAV · APE 등) | MP3 · M4A · OGG | 변환 |
| 무손실 | FLAC · WAV | 목표가 원본보다 낮으면 낮춰서 변환. 같거나 높으면 형식이 같을 때 복사, 다를 때(WAV → FLAC 등) 원본 음질로 변환 |
| 손실 (MP3 · M4A · OGG) | FLAC · WAV | 복사 (음질이 오르지 않음) |
| 손실 | MP3 · M4A · OGG | 목표 비트레이트가 원본보다 낮을 때만 변환, 아니면 복사. 원본 비트레이트를 모르면 변환 |

복사는 원본 파일을 형식 그대로 둡니다. 복사할 곳이 원본 자리(덮어쓰기)면 건너뜁니다.

---

## 📥 설치

설치 파일 `AudioConverter_<버전>_x64-setup.exe`를 실행합니다(아래 [설치 파일 만들기](#설치-파일-만들기)로 만듭니다).
관리자 권한이 필요 없고, FFmpeg가 함께 들어 있어 따로 설치하지 않아도 됩니다. OS는 Windows 10/11입니다.

설정과 오류 기록은 `%APPDATA%\AudioConverter\`(`settings.json`, `conversion_errors.log`)에 남습니다.

---

## 🖱️ 사용법

1. 음악 파일이나 폴더를 창에 끌어다 놓거나 **파일 추가** · **폴더 추가**로 대기열에 담습니다.
2. 대기열에서 원본 음질과 **할 일**(변환 · 복사 · 건너뜀)을 확인합니다. 마우스를 올리면 만들 파일 이름이 보입니다.
3. 필요하면 **설정**에서 출력 형식과 음질, 동시 변환 수, 저장 위치, 파일 이름 규칙을 바꿉니다. 바꾸면 바로 저장됩니다.
4. **변환 시작**을 누릅니다. 덮어쓰기를 골랐으면 바뀔 원본 수를 알리고 한 번 더 묻습니다.
5. 변환 중에는 '지금 변환 중' 카드에 파일마다 진행률이 보이고, 끝나면 결과 요약(LAST RUN)이 남습니다.

| 설정 | 설명 | 기본값 / 선택지 |
| --- | --- | --- |
| **출력 형식** | | MP3 / M4A · OGG · FLAC · WAV |
| **비트레이트** | MP3 · M4A · OGG | 192k / 320k · 256k · 192k · 128k |
| **비트 깊이 · 샘플레이트** | FLAC · WAV. 원본보다 높이지 않습니다 | 16bit · 44.1kHz / 24 · 16bit, 192 · 96 · 48 · 44.1kHz |
| **동시 변환** | 한 번에 변환할 파일 수 | 권장(4, 코어가 적으면 코어 수) / 1~8 |
| **저장 위치** | 원본과 같은 폴더 또는 지정 폴더 | 원본과 같은 폴더 |
| **파일 이름** | 접미사 · 접두사 붙이기 또는 같은 이름(덮어쓰기). 문구를 비우면 결과의 실제 음질을 붙입니다(`_192k`, 접두사는 `[192k]_`, 복사한 파일은 원본 음질) | 접미사, 자동 |

덮어쓰기에서 형식이 같으면(FLAC → FLAC 16bit 등) 원본을 변환한 파일로 바꿉니다. 형식이 다르면(FLAC → MP3) 원본은 그대로 두고 새 파일을 만듭니다.

---

## 🛠️ 개발

필요한 것: [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), Rust(stable MSVC), 그리고 개발 실행용 FFmpeg · ffprobe(PATH, 예: `winget install Gyan.FFmpeg`).

```bat
cd app
pnpm install
pnpm tauri dev                   :: 창으로 실행(백엔드는 셸이 uv run 으로 띄움)
```

브라우저에서 화면만 볼 때는 터미널 두 개에서:

```bat
cd backend
uv run audioconverter serve      :: http://127.0.0.1:8768
uv run audioconverter doctor     :: FFmpeg · ffprobe · 인코더(libmp3lame · aac · libvorbis · flac) 확인
uv run audioconverter convert song.flac --format mp3 --bitrate 320   :: 파일 하나 변환(시험용)
```

```bat
cd app
pnpm dev                         :: http://localhost:5176
```

브라우저에서는 끌어다 놓기와 선택 창이 없어 '경로로 추가'로 파일이나 폴더 경로를 넣습니다. 화면 규칙은 [DESIGN.md](DESIGN.md)에 있습니다.

검사:

```bat
cd backend
uv run pytest
uv run ruff check
cd ..\app
pnpm lint
pnpm build
cd ..
python scripts\check_structure.py
```

FFmpeg가 PATH에 있으면 `pytest`가 실제 변환 시험(형식별 변환, 태그 · 앨범 그림, 덮어쓰기)도 돌리고, 없으면 그 시험만 건너뜁니다.

### 설치 파일 만들기

```bat
powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
```

1. 정해 둔 FFmpeg 빌드(gyan.dev 8.1 essentials, video_converter와 같은 것)를 한 번 내려받아
   SHA-256을 확인하고 `backend\.tools`에 둡니다. 빌드하는 PC에 깔린 FFmpeg는 쓰지 않습니다(이 빌드로 시험했으므로).
2. 백엔드를 PyInstaller로 묶고 옆에 `ffmpeg.exe` · `ffprobe.exe`와 라이선스를 넣은 뒤,
   `audioconverter-backend.exe doctor --bundled`로 FFmpeg · ffprobe · 오디오 인코더가 다 있는지 확인합니다.
3. Tauri로 설치 파일을 만듭니다: `app\src-tauri\target\release\bundle\nsis\AudioConverter_<버전>_x64-setup.exe`

FFmpeg를 올리려면 `build_app.ps1`의 `$FFmpegVersion`과 `$FFmpegSha256`을 함께 바꾸고 변환을 시험합니다.
`powershell -File`로 실행하세요. PowerShell 5.1 안에서 출력을 `*>&1`로 돌리면 uv가 stderr에 쓰는 안내를 오류로 여겨 멈춥니다.

---

## 🏗️ 프로젝트 구조

| 경로 | 역할 |
| --- | --- |
| `backend/src/audioconverter/config.py` | 변환 상수, 사용자 설정(`%APPDATA%\AudioConverter\settings.json`) |
| `backend/src/audioconverter/core/service.py` | 대기열 · 오디오 분석 · 일괄 변환 · 중단 상태 |
| `backend/src/audioconverter/core/decide.py` | 변환할지 복사할지(위 표), 만들 음질 |
| `backend/src/audioconverter/core/pipeline.py` | 파일 하나: 분석 → 판단 → 변환 또는 복사 → 확인 → 바꿈 |
| `backend/src/audioconverter/core/` | 그 밖에 FFmpeg 찾기, ffprobe, FFmpeg 명령, 실행 추적, 남은 임시 파일 정리 |
| `backend/src/audioconverter/api/` | 화면이 쓰는 로컬 HTTP/WebSocket API (`base.py`는 네 앱 공통) |
| `backend/src/audioconverter/cli.py` | `serve`, `doctor`, `convert` 명령 |
| `backend/src/audioconverter/assets/` | 아이콘 원본 |
| `backend/packaging/` | PyInstaller 설정 |
| `backend/tests/` | pytest |
| `app/src/` | 화면(React): 대기열 · 설정 · 도움말. `backend.ts` · `common.tsx` · `base.css`는 네 앱 공통 |
| `app/src-tauri/` | 데스크톱 셸(Tauri): 백엔드를 띄우고 끝냄. `lib.rs`는 네 앱 공통, 앱 값은 `app_info.rs` |
| `scripts/build_app.ps1` | 설치 파일 빌드 |
| `scripts/collect_licenses.py` | 설치 파일에 넣을 서드파티 라이선스 모으기 |
| `scripts/check_structure.py` | 네 앱(jamak_converter 등)의 공통 파일이 같은지 확인. 기준은 jamak_converter의 `docs/STRUCTURE.md` |
| `THIRD_PARTY_NOTICES.md` | 함께 배포하는 구성 요소의 라이선스 안내 |
| `.github/workflows/ci.yml` | 푸시 · PR 검사 |

---

## 📄 라이선스

소스 코드는 [MIT](LICENSE)입니다. 설치 파일에 함께 들어 있는 FFmpeg(GPL-3.0) 등은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 보세요.
