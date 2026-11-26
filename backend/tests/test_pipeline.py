"""파일 하나 변환. 앞쪽은 FFmpeg 없이(실행기를 바꿔 끼워), 뒤쪽은 실제 FFmpeg 로."""

from __future__ import annotations

import json
import os
import subprocess
import threading

import pytest
from conftest import make_audio, needs_ffmpeg

from audioconverter.core import leftovers, pipeline
from audioconverter.core.decide import Target
from audioconverter.core.probe import AudioInfo

FLAC_24_96 = AudioInfo("flac", 96000, 0, 24, duration=2.0)


def leftover_parts(folder) -> list[str]:
    return [n for n in os.listdir(folder) if ".part-" in n]


def src_file(tmp_path, name="곡.flac") -> str:
    p = tmp_path / name
    p.write_bytes(b"source" * 100)
    return str(p)


class FakeRunner:
    """run_ffmpeg_and_track 대신. 명령을 기록하고, 차례대로 정해 둔 결과를 낸다."""

    def __init__(self, *results):
        self.results = list(results) or [(0, "")]
        self.cmds: list[list[str]] = []

    def __call__(self, cmd, total, progress, cancel, output_path=None):
        self.cmds.append(cmd)
        rc, err = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if rc == 0:
            with open(cmd[-1], "wb") as f:
                f.write(b"x" * 500)
        else:
            with open(cmd[-1], "wb") as f:  # 실패해도 반쯤 쓴 파일이 남을 수 있다
                f.write(b"half")
        return rc, err


@pytest.fixture
def fake(monkeypatch):
    def install(*results, info=FLAC_24_96):
        r = FakeRunner(*results)
        monkeypatch.setattr(pipeline, "run_ffmpeg_and_track", r)
        return r, (lambda _p: info)
    return install


def test_파일이_없으면_실패(tmp_path):
    r = pipeline.convert(str(tmp_path / "없음.flac"), Target("MP3"))
    assert r.status == "failed"


def test_분석에_실패하면_실패(tmp_path):
    r = pipeline.convert(src_file(tmp_path), Target("MP3"), probe_fn=lambda _p: None)
    assert r.status == "failed" and "오디오 정보" in r.message


def test_변환_성공(tmp_path, fake):
    runner, probe = fake()
    src = src_file(tmp_path)
    r = pipeline.convert(src, Target("MP3", 192), "", "suffix", "_192k", probe_fn=probe)
    assert r.status == "done" and r.message == "FLAC 24bit/96k → MP3 192k"
    assert r.output == str(tmp_path / "곡_192k.mp3") and os.path.getsize(r.output) == 500
    assert leftover_parts(tmp_path) == [] and leftovers._read() == []
    assert ".part-" in runner.cmds[0][-1], "임시 파일에 먼저 쓴다"


def test_덮어쓰기는_다_만든_뒤에_원본을_바꾼다(tmp_path, fake):
    """1.x 버그: 입력과 출력이 같으면 FFmpeg 가 거절했다."""
    runner, probe = fake()
    src = src_file(tmp_path)
    r = pipeline.convert(src, Target("FLAC", bit_depth=16, sample_rate=44100), "", "overwrite", "", probe_fn=probe)
    assert r.status == "done" and r.output == src
    assert runner.cmds[0][runner.cmds[0].index("-i") + 1] == src and runner.cmds[0][-1] != src
    assert open(src, "rb").read() == b"x" * 500


def test_실패하면_원본과_임시_파일을_남기지_않는다(tmp_path, fake):
    _runner, probe = fake((1, "Error while decoding stream\n"))
    src = src_file(tmp_path)
    r = pipeline.convert(src, Target("FLAC", bit_depth=16, sample_rate=44100), "", "overwrite", "", probe_fn=probe)
    assert r.status == "failed" and "코드 1" in r.message and "Error while decoding" in r.message
    assert open(src, "rb").read() == b"source" * 100, "덮어쓰기가 실패해도 원본은 그대로"
    assert leftover_parts(tmp_path) == [] and leftovers._read() == []
    log = os.path.join(os.environ["AUDIOCONVERTER_LOG_DIR"], "conversion_errors.log")
    assert "Error while decoding" in open(log, encoding="utf-8").read()


def test_중단(tmp_path, fake):
    _runner, probe = fake((-1, "USER_CANCELLED"))
    cancel = threading.Event()
    cancel.set()
    r = pipeline.convert(src_file(tmp_path), Target("MP3"), cancel=cancel, probe_fn=probe)
    assert r.status == "cancelled" and leftover_parts(tmp_path) == []


def test_멈추면_실패(tmp_path, fake):
    _runner, probe = fake((-1, "STUCK_TIMEOUT..."))
    r = pipeline.convert(src_file(tmp_path), Target("MP3"), probe_fn=probe)
    assert r.status == "failed" and "오래" in r.message and leftover_parts(tmp_path) == []


def test_결과가_비면_실패(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "run_ffmpeg_and_track", lambda cmd, *a, **k: (open(cmd[-1], "wb").close(), (0, ""))[1])
    r = pipeline.convert(src_file(tmp_path), Target("MP3"), probe_fn=lambda _p: FLAC_24_96)
    assert r.status == "failed" and "비어" in r.message and leftover_parts(tmp_path) == []


def test_OGG_비트레이트가_안_되면_품질_값으로(tmp_path, fake):
    runner, probe = fake((1, "[libvorbis @ 0x1] encoder setup failed\n"), (0, ""))
    r = pipeline.convert(src_file(tmp_path), Target("OGG", 320), probe_fn=probe)
    assert r.status == "done" and len(runner.cmds) == 2
    assert "-b:a" in runner.cmds[0] and "-q:a" in runner.cmds[1]


def test_앨범_그림은_따로_붙인다(tmp_path, fake):
    runner, probe = fake(info=AudioInfo("flac", 96000, 0, 24, duration=2.0, has_cover=True))
    r = pipeline.convert(src_file(tmp_path), Target("MP3"), probe_fn=probe)
    assert r.status == "done" and len(runner.cmds) == 2
    assert "attached_pic" in runner.cmds[1] and runner.cmds[1][5] == runner.cmds[0][-1], "만든 소리에 붙인다"
    assert leftover_parts(tmp_path) == [] and leftovers._read() == []


def test_앨범_그림을_못_붙이면_그림_없이_낸다(tmp_path, fake):
    runner, probe = fake((0, ""), (1, "Could not find tag for codec"),
                         info=AudioInfo("flac", 96000, 0, 24, duration=2.0, has_cover=True))
    r = pipeline.convert(src_file(tmp_path), Target("M4A"), probe_fn=probe)
    assert r.status == "done" and "앨범 그림은 넣지 못함" in r.message
    assert os.path.getsize(r.output) == 500 and leftover_parts(tmp_path) == []


def test_복사(tmp_path, fake):
    runner, probe = fake(info=AudioInfo("mp3", 44100, 128_000))
    src = src_file(tmp_path, "곡.mp3")
    r = pipeline.convert(src, Target("FLAC"), "", "suffix", "_16bit_44.1k", probe_fn=probe)
    assert r.status == "copied" and runner.cmds == []
    assert r.output == str(tmp_path / "곡_16bit_44.1k.mp3") and open(r.output, "rb").read() == open(src, "rb").read()


def test_덮어쓰기에서_복사할_것이면_건너뛴다(tmp_path, fake):
    runner, probe = fake(info=AudioInfo("mp3", 44100, 128_000))
    src = src_file(tmp_path, "곡.mp3")
    before = os.stat(src).st_mtime_ns
    r = pipeline.convert(src, Target("MP3", 320), "", "overwrite", "", probe_fn=probe)
    assert r.status == "skipped" and runner.cmds == [] and os.stat(src).st_mtime_ns == before


# ------------------------------------------------------------------ 실제 FFmpeg


def ffprobe(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,sample_rate,bits_per_raw_sample:stream_disposition=attached_pic"
                          ":format_tags=title:stream_tags=title", "-of", "json", str(path)],
                         capture_output=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


def audio_stream(data) -> dict:
    return next(s for s in data["streams"] if s["codec_type"] == "audio")


def has_cover(data) -> bool:
    return any(s["codec_type"] == "video" and s["disposition"]["attached_pic"] for s in data["streams"])


def title(data) -> str:
    """파일 태그. OGG 는 오디오 스트림에 둔다."""
    tags = {**audio_stream(data).get("tags", {}), **data.get("format", {}).get("tags", {})}
    return next((v for k, v in tags.items() if k.lower() == "title"), "")


@needs_ffmpeg
@pytest.mark.parametrize(("target", "codec", "cover"), [
    (Target("MP3", 192), "mp3", True),
    (Target("M4A", 128), "aac", True),
    (Target("OGG", 128), "vorbis", False),
    (Target("FLAC", bit_depth=16, sample_rate=44100), "flac", True),
    (Target("WAV", bit_depth=16, sample_rate=44100), "pcm_s16le", False),
])
def test_실제_형식별_변환_태그와_앨범_그림(tmp_path, target, codec, cover):
    src = make_audio(tmp_path / "원본.flac", rate=96000, fmt="s32", seconds=20, title="테스트 곡", cover=True)
    seen = []
    r = pipeline.convert(src, target, str(tmp_path / "out"), "suffix", f"_{target.affix}",
                         progress=lambda pct, t, s: seen.append(pct))
    assert r.status == "done", r.message
    data = ffprobe(r.output)
    assert audio_stream(data)["codec_name"] == codec
    assert has_cover(data) is cover
    if target.format != "WAV":  # WAV 의 태그(RIFF INFO)는 ffprobe 가 format 이 아니라 다른 곳에 둔다
        assert title(data) == "테스트 곡"
    assert seen and max(seen) > 50, "앨범 그림이 있어도 진행률이 나온다"
    assert leftover_parts(tmp_path / "out") == [] and leftovers._read() == []


@needs_ffmpeg
def test_실제_FLAC_24비트(tmp_path):
    src = make_audio(tmp_path / "a.flac", rate=96000, fmt="s32")
    r = pipeline.convert(src, Target("FLAC", bit_depth=24, sample_rate=48000), "", "suffix", "_x")
    s = audio_stream(ffprobe(r.output))
    assert r.status == "done" and s["sample_rate"] == "48000" and s["bits_per_raw_sample"] == "24"


@needs_ffmpeg
def test_실제_덮어쓰기(tmp_path):
    tmp_path = tmp_path / "music"
    tmp_path.mkdir()
    src = make_audio(tmp_path / "a.flac", rate=96000, fmt="s32", title="곡")
    r = pipeline.convert(src, Target("FLAC", bit_depth=16, sample_rate=44100), "", "overwrite", "")
    assert r.status == "done" and r.output == src
    s = audio_stream(ffprobe(src))
    assert s["sample_rate"] == "44100" and s["bits_per_raw_sample"] == "16"
    again = pipeline.convert(src, Target("FLAC", bit_depth=16, sample_rate=44100), "", "overwrite", "")
    assert again.status == "skipped"
    assert sorted(os.listdir(tmp_path)) == ["a.flac"]


@needs_ffmpeg
def test_실제_덮어쓰기_다른_형식은_원본을_남긴다(tmp_path):
    tmp_path = tmp_path / "music"
    tmp_path.mkdir()
    src = make_audio(tmp_path / "a.flac")
    r = pipeline.convert(src, Target("MP3", 128), "", "overwrite", "")
    assert r.status == "done" and sorted(os.listdir(tmp_path)) == ["a.flac", "a.mp3"]


@needs_ffmpeg
def test_실제_OGG_모노_저샘플레이트(tmp_path):
    """libvorbis 는 모노 22kHz 에 320k 를 받지 않는다. 품질 값으로 다시 만든다."""
    src = str(tmp_path / "m.flac")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=f=440:d=2:sample_rate=22050", "-ac", "1", "-c:a", "flac", src], check=True)
    r = pipeline.convert(src, Target("OGG", 320), "", "suffix", "_320k")
    assert r.status == "done", r.message
    assert audio_stream(ffprobe(r.output))["codec_name"] == "vorbis"


@needs_ffmpeg
def test_실제_오디오가_아닌_파일(tmp_path):
    p = tmp_path / "가짜.mp3"
    p.write_text("not audio", encoding="utf-8")
    assert pipeline.convert(str(p), Target("MP3")).status == "failed"


@needs_ffmpeg
def test_실제_손실_원본은_더_높은_비트레이트로_만들지_않는다(tmp_path):
    src = make_audio(tmp_path / "a.mp3", codec="libmp3lame", bitrate="128k")
    r = pipeline.convert(src, Target("MP3", 320), "", "suffix", "_320k")
    assert r.status == "copied" and open(r.output, "rb").read() == open(src, "rb").read()
    r = pipeline.convert(src, Target("OGG", 128), "", "suffix", "_128k")
    assert r.status == "copied"
