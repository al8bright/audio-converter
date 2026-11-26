"""FFmpeg 명령, 출력 경로, 임시 파일, 실패 사유 요약."""

from __future__ import annotations

import os
import time
import uuid

from ..config import FFMPEG_STDERR_MAX_LINES, FFMPEG_STDERR_SKIP_PREFIXES, LOSSY_MAX_SAMPLE_RATE
from . import tools
from .decide import Target
from .probe import AudioInfo

# 앨범 그림을 담을 수 있는 형식. OGG 는 FFmpeg 가 그림을 Theora 영상으로 만들고, WAV 는 담을 곳이 없다.
# 그림은 소리를 다 만든 뒤 따로 붙인다(build_cover_cmd). 처음부터 함께 넣으면 FFmpeg 가 진행 시간을 N/A 로만 알린다
COVER_FORMATS = frozenset({"MP3", "M4A", "FLAC"})

# libvorbis 는 채널 수·샘플레이트에 따라 받는 비트레이트가 정해져 있어(예: 모노 22kHz 에 320k 는 시작 실패)
# 그때는 품질 값으로 다시 만든다. 스테레오 44.1kHz 에서 비트레이트가 비슷한 값
VORBIS_QUALITY = {320: 9, 256: 8, 192: 6, 128: 4}


def resolve_output_path(src: str, out_dir: str, name_mode: str, value: str, ext: str) -> str:
    """결과 경로. out_dir 가 비면 원본 폴더. name_mode: suffix | prefix | overwrite"""
    folder = os.path.abspath(out_dir) if out_dir else os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    if name_mode == "suffix":
        name = f"{stem}{value}{ext}"
    elif name_mode == "prefix":
        name = f"{value}{stem}{ext}"
    else:
        name = f"{stem}{ext}"
    return os.path.join(folder, name)


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def build_encode_cmd(src: str, out: str, target: Target, info: AudioInfo, vorbis_quality: bool = False) -> list[str]:
    """첫 오디오 스트림과 태그만 담는다(그림은 build_cover_cmd)."""
    cmd = [tools.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-i", src, "-map", "0:a:0", "-map_metadata", "0"]
    fmt = target.format
    if fmt == "WAV":
        cmd += ["-c:a", "pcm_s24le" if target.bit_depth == 24 else "pcm_s16le", "-ar", str(target.sample_rate)]
    elif fmt == "FLAC":
        cmd += ["-c:a", "flac", "-sample_fmt", "s32" if target.bit_depth == 24 else "s16"]
        if target.bit_depth == 24:
            cmd += ["-bits_per_raw_sample", "24"]
        cmd += ["-ar", str(target.sample_rate)]
    else:
        if fmt == "MP3":
            cmd += ["-c:a", "libmp3lame", "-b:a", f"{target.bitrate}k", "-id3v2_version", "3"]
        elif fmt == "M4A":
            cmd += ["-c:a", "aac", "-b:a", f"{target.bitrate}k"]
        elif vorbis_quality:
            cmd += ["-c:a", "libvorbis", "-q:a", str(VORBIS_QUALITY.get(target.bitrate, 6))]
        else:
            cmd += ["-c:a", "libvorbis", "-b:a", f"{target.bitrate}k"]
        if info.sample_rate > LOSSY_MAX_SAMPLE_RATE:
            cmd += ["-ar", str(LOSSY_MAX_SAMPLE_RATE)]
    cmd.append(out)
    return cmd


def wants_cover(info: AudioInfo, target: Target) -> bool:
    return info.has_cover and target.format in COVER_FORMATS


def build_cover_cmd(audio: str, src: str, out: str, target: Target) -> list[str]:
    """만든 소리(audio)에 원본(src)의 앨범 그림을 다시 인코딩하지 않고 붙인다."""
    cmd = [tools.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-i", audio, "-i", src,
           "-map", "0:a", "-map", "1:v:0", "-c", "copy", "-disposition:v:0", "attached_pic", "-map_metadata", "0"]
    if target.format == "MP3":
        cmd += ["-id3v2_version", "3"]
    return [*cmd, out]


def vorbis_setup_failed(stderr: str) -> bool:
    low = (stderr or "").lower()
    return "libvorbis" in low and "encoder setup failed" in low


def summarize_stderr(stderr: str) -> str:
    """시작 로그(버전·설정·라이브러리)를 걸러 마지막 몇 줄로 줄인다."""
    if not stderr or not stderr.strip():
        return "(stderr 없음)"
    lines = [ln.strip() for ln in stderr.strip().splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.startswith(FFMPEG_STDERR_SKIP_PREFIXES)]
    if len(lines) <= FFMPEG_STDERR_MAX_LINES:
        return "\n".join(lines)
    head = 5
    tail = FFMPEG_STDERR_MAX_LINES - head - 1
    return "\n".join(lines[:head] + ["..."] + lines[-tail:])


# errorlog.py 는 video_converter 와 같은 이름으로 부른다
_summarize_ffmpeg_stderr = summarize_stderr


def last_error_line(stderr: str) -> str:
    """화면에 보일 한 줄: 진행 줄이 아닌 마지막 줄."""
    for ln in reversed((stderr or "").strip().splitlines()):
        ln = ln.strip()
        if ln and "time=" not in ln and not ln.startswith(FFMPEG_STDERR_SKIP_PREFIXES):
            return ln[:200]
    return ""


def tmp_output_path(dest: str) -> str:
    """`<결과>.part-<pid>-<hex8><확장자>`. 확장자를 남겨야 FFmpeg 가 형식을 안다."""
    ext = os.path.splitext(dest)[1]
    return f"{dest}.part-{os.getpid()}-{uuid.uuid4().hex[:8]}{ext}"


def tmp_is_valid(path: str, min_bytes: int = 64) -> bool:
    try:
        return os.path.getsize(path) > min_bytes
    except OSError:
        return False


def safe_remove(path: str | None, wait: float = 2.0) -> None:
    """있으면 지운다. 실패해도 예외를 내지 않는다.

    FFmpeg 를 끊은 직후에는 파일이 아직 잡혀 있을 수 있다(Chocolatey 등의 대리 실행 파일 뒤의 진짜 ffmpeg 가
    조금 늦게 끝난다). 잠겨 있으면 wait 초까지 다시 시도한다.
    """
    if not path:
        return
    deadline = time.monotonic() + wait
    while True:
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.1)
        except OSError:
            return
