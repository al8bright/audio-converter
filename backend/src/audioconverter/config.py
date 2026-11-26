r"""변환 상수와 데이터 폴더.

데이터(설정, 오류 기록)는 %APPDATA%\AudioConverter 에 둔다(AUDIOCONVERTER_HOME 으로 바꿀 수 있다).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

SUPPORTED_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav", ".ape", ".dsf", ".dff")

# 출력 형식. 손실 형식은 비트레이트, 무손실 형식은 비트 깊이와 샘플레이트로 음질을 정한다
Format = Literal["MP3", "M4A", "OGG", "FLAC", "WAV"]
FORMATS: tuple[str, ...] = ("MP3", "M4A", "OGG", "FLAC", "WAV")
LOSSLESS_FORMATS = frozenset({"FLAC", "WAV"})
EXTENSIONS = {"MP3": ".mp3", "M4A": ".m4a", "OGG": ".ogg", "FLAC": ".flac", "WAV": ".wav"}
BITRATES = (320, 256, 192, 128)  # kbps
BIT_DEPTHS = (24, 16)
SAMPLE_RATES = (192000, 96000, 48000, 44100)
Bitrate = Literal[320, 256, 192, 128]
BitDepth = Literal[24, 16]
SampleRate = Literal[192000, 96000, 48000, 44100]
SaveMode = Literal["same", "folder"]
NameMode = Literal["suffix", "prefix", "overwrite"]
Sidebar = Literal["open", "closed"]

# 동시 변환 수. 오디오 인코더는 파일 하나에 CPU 코어 하나쯤을 쓴다. 권장값은 4개(코어가 적으면 코어 수)
MAX_SLOTS = 8
DEFAULT_JOBS = 4

# 손실 형식은 이보다 높은 샘플레이트로 만들지 않는다. libvorbis 는 96kHz 원본이면 시작조차 못 하고,
# LAME 은 스스로 48kHz 로 내린다. 사람이 듣는 범위에서 차이가 없어 세 형식을 같게 둔다
LOSSY_MAX_SAMPLE_RATE = 48000

# 진행(time=)이 이 시간(초)을 넘도록 바뀌지 않으면 FFmpeg 가 멈춘 것으로 보고 끝낸다
STUCK_TIMEOUT_SEC = 300

# 실패 사유를 줄일 때 걸러낼 FFmpeg 시작 로그와 남길 줄 수
FFMPEG_STDERR_SKIP_PREFIXES = (
    "ffmpeg version", "built with", "configuration:", "libavutil",
    "libavcodec", "libavformat", "libavdevice", "libavfilter",
    "libswscale", "libswresample",
)
FFMPEG_STDERR_MAX_LINES = 20


def app_home() -> Path:
    override = os.environ.get("AUDIOCONVERTER_HOME")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "AudioConverter"


def recommended_jobs() -> int:
    return max(1, min(DEFAULT_JOBS, os.cpu_count() or 1))


class Settings(BaseModel):
    jobs: int | None = Field(default=None, ge=1, le=MAX_SLOTS)  # None 이면 권장값(recommended_jobs)
    format: Format = "MP3"
    bitrate: Bitrate = 192  # MP3·M4A·OGG
    bit_depth: BitDepth = 16  # FLAC·WAV
    sample_rate: SampleRate = 44100  # FLAC·WAV
    save_mode: SaveMode = "same"
    save_dir: str = ""  # save_mode 가 folder 일 때만 쓴다
    name_mode: NameMode = "suffix"
    # 이름에 붙일 문구. 비우면 결과의 음질로 정한다(접미사 _192k, 접두사 [192k]_)
    name_text: str = Field(default="", max_length=40)
    sidebar: Sidebar = "open"  # 사이드바 접기/펴기. 다음 실행에도 그대로 연다


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_home() / "settings.json"
        self.lock = threading.Lock()
        self.value = self._load()

    def _load(self) -> Settings:
        try:
            return Settings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return Settings()

    def get(self) -> Settings:
        with self.lock:
            return self.value.model_copy()

    def save(self, value: Settings) -> None:
        with self.lock:
            self.value = value.model_copy()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
