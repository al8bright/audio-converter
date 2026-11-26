"""테스트 공통: 데이터 폴더를 임시 폴더로 돌리고, 실제 FFmpeg 가 필요한 시험은 없으면 건너뛴다."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from audioconverter.config import Settings, SettingsStore
from audioconverter.core.pipeline import Result
from audioconverter.core.probe import AudioInfo
from audioconverter.core.service import Service


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """로그·설정·임시 파일 기록이 사용자 데이터 폴더에 쌓이지 않게 한다."""
    monkeypatch.setenv("AUDIOCONVERTER_LOG_DIR", str(tmp_path / "aclogs"))
    monkeypatch.setenv("AUDIOCONVERTER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AUDIOCONVERTER_TOOLS_DIR", raising=False)


@pytest.fixture
def tools_dir(tmp_path, monkeypatch):
    """ffmpeg·ffprobe 가 있는 것처럼 보이는 폴더(실행하지는 않는다)."""
    d = tmp_path / "tools"
    d.mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
        (d / name).write_bytes(b"")
    monkeypatch.setenv("AUDIOCONVERTER_TOOLS_DIR", str(d))
    return d


HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg·ffprobe 가 PATH 에 없다")


def make_audio(path, *, codec: str = "flac", rate: int = 44100, seconds: float = 2, fmt: str | None = None,
               bitrate: str | None = None, title: str = "", cover: bool = False) -> str:
    """FFmpeg 로 사인파 오디오를 만든다. cover 면 작은 앨범 그림을 붙인다."""
    path = str(path)
    ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    # 그림은 따로 만들어 붙인다. 한 명령에서 -frames:v 1 을 주면 소리까지 거기서 끝난다
    out = f"{path}.raw{os.path.splitext(path)[1]}" if cover else path
    cmd = [*ff, "-f", "lavfi", "-i", f"sine=f=440:d={seconds}:sample_rate={rate}", "-ac", "2", "-c:a", codec]
    if fmt:
        cmd += ["-sample_fmt", fmt]
    if bitrate:
        cmd += ["-b:a", bitrate]
    if title:
        cmd += ["-metadata", f"title={title}"]
    if codec == "libmp3lame":
        cmd += ["-id3v2_version", "3"]
    subprocess.run([*cmd, out], check=True)
    if cover:
        jpg = f"{path}.jpg"
        subprocess.run([*ff, "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", jpg], check=True)
        subprocess.run([*ff, "-i", out, "-i", jpg, "-map", "0", "-map", "1", "-c", "copy",
                        "-disposition:v:0", "attached_pic", path], check=True)
        os.remove(out)
        os.remove(jpg)
    return path


# ------------------------------------------------------------------ Service (FFmpeg·스레드 없이)

INFO = AudioInfo("flac", 96000, 0, 24, 2, 180.0)


def audio(folder, name: str, data: bytes = b"a" * 100) -> str:
    """빈 오디오 파일을 만든다(내용은 보지 않는다)."""
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p)


class FakeConvert:
    """pipeline.convert 대신. 파일 이름별로 결과를 정하고, 받은 인자를 기록한다."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.results: dict[str, object] = {}  # 파일 이름 -> Result | 예외 | callable(progress, cancel)

    def __call__(self, path, target, out_dir, name_mode, value, progress, cancel):
        self.calls.append({"path": path, "target": target, "out_dir": out_dir, "name_mode": name_mode,
                           "value": value})
        r = self.results.get(os.path.basename(path))
        if r is None:
            r = Result("done", "FLAC 24bit/96k → MP3 192k", os.path.splitext(path)[0] + "_192k.mp3")
        if isinstance(r, BaseException):
            raise r
        if callable(r):
            return r(progress, cancel)
        progress(50.0, "00:01:30.00", "80x")
        return r


def run_now(fn, *args):
    """스레드 대신 그 자리에서 돌린다."""
    fn(*args)


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "settings.json")


@pytest.fixture
def convert():
    return FakeConvert()


@pytest.fixture
def probes():
    """파일 이름 -> AudioInfo(None 이면 실패). 없으면 INFO."""
    return {}


@pytest.fixture
def killed():
    return []


@pytest.fixture
def make_svc(store, convert, probes, killed, tools_dir):
    def make(spawn=run_now, recommended=4):
        return Service(settings=store, convert=convert, spawn=spawn, kill=lambda: killed.append(1),
                       probe=lambda p: probes.get(os.path.basename(p), INFO),
                       detect=lambda: {"cpu_count": 8, "recommended_jobs": recommended})

    return make


@pytest.fixture
def svc(make_svc):
    return make_svc()


__all__ = ["INFO", "FakeConvert", "Result", "Settings", "audio", "make_audio", "needs_ffmpeg", "run_now"]
