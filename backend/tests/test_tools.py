"""FFmpeg 찾기: 함께 넣은 것 → PATH."""

import os

from audioconverter.core import tools
from audioconverter.core.decide import Target
from audioconverter.core.ffmpeg_cmd import build_encode_cmd
from audioconverter.core.probe import AudioInfo


def test_도구_폴더의_것을_먼저_쓴다(tools_dir):
    assert os.path.dirname(tools.ffmpeg()) == str(tools_dir)
    assert os.path.dirname(tools.ffprobe()) == str(tools_dir)
    cmd = build_encode_cmd("in.flac", "out.mp3", Target("MP3"), AudioInfo("flac", 44100))
    assert cmd[0] == tools.ffmpeg()


def test_도구_폴더에_없으면_없다고_한다(tmp_path, monkeypatch):
    monkeypatch.setenv(tools.TOOLS_DIR_ENV, str(tmp_path))
    assert tools.bundled_tool("ffmpeg") is None


def test_어디에도_없으면_이름만_돌려준다(tmp_path, monkeypatch):
    monkeypatch.delenv(tools.TOOLS_DIR_ENV, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert tools.tool_path("ffmpeg") is None
    assert tools.ffmpeg() == "ffmpeg"
