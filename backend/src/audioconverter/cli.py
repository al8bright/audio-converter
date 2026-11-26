"""명령줄 진입점: `audioconverter serve`, `audioconverter doctor`, `audioconverter convert`."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading

from audioconverter import __version__
from audioconverter.config import BIT_DEPTHS, BITRATES, FORMATS, SAMPLE_RATES

# 출력 형식마다 쓰는 인코더. FLAC·WAV(pcm)는 FFmpeg 에 늘 들어 있다
ENCODERS = (("mp3", "libmp3lame"), ("m4a", "aac"), ("ogg", "libvorbis"), ("flac", "flac"))


def _first_line(cmd: list[str]) -> str:
    """명령을 실행해 표준 출력 첫 줄을 돌려준다. 실행하지 못하면 빈 문자열."""
    from audioconverter.core.proc import CREATE_NO_WINDOW

    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=30, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.splitlines()[0].strip() if out.returncode == 0 and out.stdout else ""


def cmd_doctor(args: argparse.Namespace) -> int:
    """변환에 필요한 것이 있는지 확인한다. --bundled 는 설치 파일을 만들기 전에 쓴다."""
    from audioconverter.config import recommended_jobs
    from audioconverter.core import tools
    from audioconverter.core.proc import CREATE_NO_WINDOW

    ok = True

    def row(name: str, good: bool | None, detail: str) -> None:
        nonlocal ok
        ok = ok and good is not False
        mark = "--" if good is None else "OK" if good else "NO"
        print(f"[{mark}] {name:<8} {detail}")

    for name in ("ffmpeg", "ffprobe"):
        path = tools.bundled_tool(name) if args.bundled else tools.tool_path(name)
        version = _first_line([path, "-version"]) if path else ""
        where = "next to the executable" if args.bundled else "on PATH (winget install Gyan.FFmpeg)"
        row(name, bool(version), f"{version} ({path})" if version else f"{path} does not run" if path else f"not found {where}")

    ffmpeg = tools.bundled_tool("ffmpeg") if args.bundled else tools.tool_path("ffmpeg")
    encoders = ""
    if ffmpeg:
        try:
            encoders = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=30,
                                      creationflags=CREATE_NO_WINDOW).stdout
        except (OSError, subprocess.SubprocessError):
            encoders = ""
    names = {line.split()[1] for line in encoders.splitlines() if len(line.split()) > 1}
    for label, enc in ENCODERS:
        have = enc in names
        row(label, have, f"{enc} in this FFmpeg" if have else f"{enc} missing")
    row("cpu", None, f"{os.cpu_count()} cores, {recommended_jobs()} jobs recommended")
    return 0 if ok else 1


def cmd_convert(args: argparse.Namespace) -> int:
    from audioconverter.core.decide import Target
    from audioconverter.core.pipeline import convert

    target = Target(args.format.upper(), args.bitrate, args.depth, args.rate)

    def progress(pct: float, time: str, speed: str) -> None:
        print(f"\r{pct:5.1f}%  {time}  {speed}   ", end="", flush=True)

    cancel = threading.Event()
    try:
        # value 가 None 이면 이름에 붙일 문구를 결과의 음질로 정한다(_192k)
        r = convert(args.file, target, args.out, args.name, args.value, progress, cancel)
    except KeyboardInterrupt:
        cancel.set()
        return 130
    print(f"\r[{r.status}] {r.message}" + (f"\n -> {r.output}" if r.output else ""))
    return 0 if r.status in ("done", "copied", "skipped") else 1


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="audioconverter", description="Audio Converter backend")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    from audioconverter.api.base import add_serve_command

    add_serve_command(sub)

    d = sub.add_parser("doctor", help="check FFmpeg, ffprobe and the audio encoders")
    d.add_argument("--bundled", action="store_true", help="require the FFmpeg shipped next to the executable")
    d.set_defaults(fn=cmd_doctor)

    c = sub.add_parser("convert", help="convert one file (for testing)")
    c.add_argument("file")
    c.add_argument("--format", required=True, type=str.upper, choices=FORMATS)
    c.add_argument("--bitrate", type=int, default=192, choices=BITRATES, help="kbps, MP3/M4A/OGG")
    c.add_argument("--depth", type=int, default=16, choices=BIT_DEPTHS, help="FLAC/WAV")
    c.add_argument("--rate", type=int, default=44100, choices=SAMPLE_RATES, help="Hz, FLAC/WAV")
    c.add_argument("--out", default="", help="output folder (default: next to the file)")
    c.add_argument("--name", default="suffix", choices=("suffix", "prefix", "overwrite"))
    c.add_argument("--value", help="suffix or prefix (default: from the result's quality, e.g. _192k)")
    c.set_defaults(fn=cmd_convert)

    args = p.parse_args(argv)
    sys.exit(args.fn(args))
