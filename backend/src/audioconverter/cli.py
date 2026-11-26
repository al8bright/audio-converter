"""명령줄: `audioconverter convert` (파일 하나 변환)."""

from __future__ import annotations

import argparse
import sys
import threading

from audioconverter import __version__
from audioconverter.config import BIT_DEPTHS, BITRATES, FORMATS, SAMPLE_RATES


def cmd_convert(args: argparse.Namespace) -> int:
    from audioconverter.core.decide import Target
    from audioconverter.core.pipeline import convert

    target = Target(args.format.upper(), args.bitrate, args.depth, args.rate)
    value = args.value if args.value is not None else (
        f"_{target.affix}" if args.name == "suffix" else f"[{target.affix}]_" if args.name == "prefix" else "")

    def progress(pct: float, time: str, speed: str) -> None:
        print(f"\r{pct:5.1f}%  {time}  {speed}   ", end="", flush=True)

    cancel = threading.Event()
    try:
        r = convert(args.file, target, args.out, args.name, value, progress, cancel)
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

    c = sub.add_parser("convert", help="convert one file (for testing)")
    c.add_argument("file")
    c.add_argument("--format", required=True, type=str.upper, choices=FORMATS)
    c.add_argument("--bitrate", type=int, default=192, choices=BITRATES, help="kbps, MP3/M4A/OGG")
    c.add_argument("--depth", type=int, default=16, choices=BIT_DEPTHS, help="FLAC/WAV")
    c.add_argument("--rate", type=int, default=44100, choices=SAMPLE_RATES, help="Hz, FLAC/WAV")
    c.add_argument("--out", default="", help="output folder (default: next to the file)")
    c.add_argument("--name", default="suffix", choices=("suffix", "prefix", "overwrite"))
    c.add_argument("--value", help="suffix or prefix (default: from the quality, e.g. _192k)")
    c.set_defaults(fn=cmd_convert)

    args = p.parse_args(argv)
    sys.exit(args.fn(args))
