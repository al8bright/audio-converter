"""ffprobe 로 오디오 규격을 읽는다."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass

from . import tools

SUBPROC_TEXT = {"encoding": "utf-8", "errors": "replace"}

LOSSLESS_CODECS = ("flac", "alac", "ape", "wav", "pcm", "dsd", "tta", "wavpack", "mlp", "truehd")


@dataclass(frozen=True)
class AudioInfo:
    codec: str  # ffprobe 의 codec_name (소문자)
    sample_rate: int = 0  # Hz
    bit_rate: int = 0  # bps. 모르면 0
    bit_depth: int = 16
    channels: int = 2
    duration: float = 0.0  # 초. 모르면 0
    has_cover: bool = False  # 앨범 그림(attached_pic)이 있음

    @property
    def dsd(self) -> str:
        """DSD 원본이면 DSD64·DSD128·DSD256, 아니면 빈 문자열."""
        if "dsd" not in self.codec:
            return ""
        if self.sample_rate >= 11_289_600:
            return "DSD256"
        if self.sample_rate >= 5_644_800:
            return "DSD128"
        if self.sample_rate >= 2_822_400:
            return "DSD64"
        return "DSD"

    @property
    def lossless(self) -> bool:
        return any(c in self.codec for c in LOSSLESS_CODECS)

    @property
    def label(self) -> str:
        """화면에 보일 원본 형식: FLAC, MP3, DSD128 등."""
        return self.dsd or self.codec.upper()

    def to_dict(self) -> dict:
        return {**asdict(self), "dsd": self.dsd, "lossless": self.lossless, "label": self.label}


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _bit_depth(stream: dict) -> int:
    raw = stream.get("bits_per_raw_sample")
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return int(raw)
    fmt = stream.get("sample_fmt", "")
    if any(f in fmt for f in ("s32", "flt", "dbl")):
        return 24
    return 16


def parse(data: dict) -> AudioInfo | None:
    """ffprobe -of json 결과에서 첫 오디오 스트림을 읽는다. 오디오가 없으면 None."""
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        return None
    cover = any(s.get("codec_type") == "video" and (s.get("disposition") or {}).get("attached_pic") for s in streams)
    try:
        duration = float((data.get("format") or {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    return AudioInfo(
        codec=(audio.get("codec_name") or "").lower(),
        sample_rate=_int(audio.get("sample_rate")),
        # 스트림 비트레이트만 본다. 파일 전체 값은 앨범 그림까지 더해져 실제보다 높게 나온다
        bit_rate=_int(audio.get("bit_rate")),
        bit_depth=_bit_depth(audio),
        channels=_int(audio.get("channels")) or 2,
        duration=duration,
        has_cover=cover,
    )


def probe(path: str) -> AudioInfo | None:
    """실패하면 None."""
    cmd = [
        tools.ffprobe(), "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,bit_rate,sample_rate,bits_per_raw_sample,sample_fmt,channels"
        ":stream_disposition=attached_pic:format=duration",
        "-of", "json", path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, check=True, timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                           **SUBPROC_TEXT)
        return parse(json.loads(r.stdout))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ffprobe 에러 ({path}): {exc}", file=sys.stderr)
        return None


def time_to_seconds(t: str) -> float | None:
    """FFmpeg 진행 줄의 time=HH:MM:SS.ss 를 초로."""
    try:
        h, m, s = t.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except ValueError:
        return None
