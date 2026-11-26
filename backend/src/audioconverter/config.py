r"""변환 상수와 데이터 폴더.

데이터(설정, 오류 기록)는 %APPDATA%\AudioConverter 에 둔다(AUDIOCONVERTER_HOME 으로 바꿀 수 있다).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

SUPPORTED_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav", ".ape", ".dsf", ".dff")

# 출력 형식. 손실 형식은 비트레이트, 무손실 형식은 비트 깊이와 샘플레이트로 음질을 정한다
Format = Literal["MP3", "M4A", "OGG", "FLAC", "WAV"]
FORMATS: tuple[str, ...] = ("MP3", "M4A", "OGG", "FLAC", "WAV")
LOSSLESS_FORMATS = frozenset({"FLAC", "WAV"})
EXTENSIONS = {"MP3": ".mp3", "M4A": ".m4a", "OGG": ".ogg", "FLAC": ".flac", "WAV": ".wav"}
BITRATES = (320, 256, 192, 128)  # kbps
BIT_DEPTHS = (24, 16)
SAMPLE_RATES = (192000, 96000, 48000, 44100)

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
