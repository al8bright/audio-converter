"""변환할지 복사할지. "음질은 원본보다 높일 수 없다" 는 규칙(PLAN.md 의 표).

| 원본 | 목표 | 동작 |
| DSD | 모든 형식 | 변환 |
| 무손실 | 손실 | 변환 |
| 무손실 | 무손실 | 목표(비트 깊이 × 샘플레이트)가 원본보다 낮을 때만 변환, 아니면 복사 |
| 손실 | 무손실 | 복사 |
| 손실 | 손실 | 목표 비트레이트가 원본보다 낮을 때만 변환, 아니면 복사. 원본 비트레이트를 모르면 변환 |

복사는 원본 파일을 형식 그대로 둔다(확장자도 원본 것). 1.x 는 목표 형식의 컨테이너에 스트림을 옮겨 담으려
해서 MP3 → FLAC 은 실패하고 FLAC → WAV 는 플레이어가 못 여는 파일이 됐다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..config import LOSSLESS_FORMATS
from .probe import AudioInfo

Action = Literal["encode", "copy"]


@dataclass(frozen=True)
class Target:
    format: str  # MP3, M4A, OGG, FLAC, WAV
    bitrate: int = 192  # kbps. 손실 형식만
    bit_depth: int = 16  # 무손실 형식만
    sample_rate: int = 44100  # 무손실 형식만

    @property
    def lossless(self) -> bool:
        return self.format in LOSSLESS_FORMATS

    @property
    def spec(self) -> str:
        """192k, 24bit/96k"""
        if self.lossless:
            return f"{self.bit_depth}bit/{khz(self.sample_rate)}k"
        return f"{self.bitrate}k"

    @property
    def label(self) -> str:
        """MP3 192k, FLAC 24bit/96k"""
        return f"{self.format} {self.spec}"

    @property
    def affix(self) -> str:
        """파일 이름에 붙일 기본 문구: 192k, 24bit_96k"""
        return self.spec.replace("/", "_")


def khz(rate: int) -> str:
    """44100 -> 44.1, 96000 -> 96"""
    v = rate / 1000
    return f"{v:g}"


def decide(info: AudioInfo, target: Target) -> Action:
    if info.dsd:
        return "encode"
    if info.lossless:
        if not target.lossless:
            return "encode"
        return "encode" if target.bit_depth * target.sample_rate < info.bit_depth * info.sample_rate else "copy"
    if target.lossless:
        return "copy"
    if info.bit_rate <= 0:
        return "encode"
    return "encode" if target.bitrate < info.bit_rate / 1000 else "copy"


def source_affix(info: AudioInfo) -> str:
    """원본 그대로 복사한 파일 이름에 붙일 문구: 16bit_44.1k, 128k. 비트레이트를 모르면 코덱 이름(aac)."""
    if info.lossless and not info.dsd:
        return f"{info.bit_depth}bit_{khz(info.sample_rate)}k"
    if info.bit_rate:
        return f"{round(info.bit_rate / 1000)}k"
    return info.label.lower()


def auto_value(name_mode: str, affix: str) -> str:
    """자동 이름 규칙: 접미사 _192k, 접두사 [192k]_, 덮어쓰기는 없음."""
    if name_mode == "suffix":
        return f"_{affix}"
    if name_mode == "prefix":
        return f"[{affix}]_"
    return ""


def source_spec(info: AudioInfo) -> str:
    """원본 음질: DSD128, 24bit/96k, 320k (비트레이트를 모르면 '?k')"""
    if info.dsd:
        return info.dsd
    if info.lossless:
        return f"{info.bit_depth}bit/{khz(info.sample_rate)}k"
    return f"{round(info.bit_rate / 1000)}k" if info.bit_rate else "?k"
