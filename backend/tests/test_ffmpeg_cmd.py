"""출력 경로, 형식별 FFmpeg 명령, 실패 사유 요약."""

import os

import pytest

from audioconverter.core.decide import Target
from audioconverter.core.ffmpeg_cmd import (
    build_cover_cmd,
    build_encode_cmd,
    last_error_line,
    resolve_output_path,
    same_path,
    summarize_stderr,
    tmp_output_path,
    vorbis_setup_failed,
    wants_cover,
)
from audioconverter.core.pipeline import plan_output
from audioconverter.core.probe import AudioInfo

SRC = os.path.join("C:\\", "music", "앨범", "01 곡.flac")
FLAC_24_96 = AudioInfo("flac", 96000, 0, 24, has_cover=True)
MP3_128 = AudioInfo("mp3", 44100, 128_000)


def args_after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


@pytest.mark.parametrize(("mode", "value", "out_dir", "name"), [
    ("suffix", "_192k", "", "01 곡_192k.mp3"),
    ("prefix", "[192k]_", "", "[192k]_01 곡.mp3"),
    ("overwrite", "", "", "01 곡.mp3"),
])
def test_출력_경로_이름_규칙(mode, value, out_dir, name):
    assert resolve_output_path(SRC, out_dir, mode, value, ".mp3") == os.path.join(os.path.dirname(SRC), name)


def test_출력_경로_지정_폴더(tmp_path):
    assert resolve_output_path(SRC, str(tmp_path), "suffix", "_x", ".ogg") == str(tmp_path / "01 곡_x.ogg")


def test_같은_경로는_대소문자와_상대경로를_가리지_않는다(tmp_path):
    a = str(tmp_path / "A.flac")
    if os.name == "nt":
        assert same_path(a, a.upper())
    assert same_path(a, os.path.join(str(tmp_path), ".", "A.flac"))


def test_복사는_원본_확장자를_쓴다():
    """1.x 는 MP3 를 FLAC 컨테이너에 옮겨 담으려다 실패했다."""
    action, dest, same = plan_output(SRC.replace(".flac", ".mp3"), MP3_128, Target("FLAC"), "", "suffix", "_16bit_44.1k")
    assert action == "copy" and dest.endswith("01 곡_16bit_44.1k.mp3") and not same


def test_덮어쓰기에서_복사할_것이면_같은_경로로_알린다():
    action, dest, same = plan_output(SRC, AudioInfo("flac", 44100, 0, 16), Target("FLAC"), "", "overwrite", "")
    assert (action, same) == ("copy", True) and dest == SRC


def test_덮어쓰기라도_형식이_다르면_원본과_다른_경로다():
    action, dest, same = plan_output(SRC, FLAC_24_96, Target("MP3"), "", "overwrite", "")
    assert action == "encode" and dest.endswith("01 곡.mp3") and not same


def test_임시_파일은_결과_옆에_확장자를_지켜_만든다():
    tmp = tmp_output_path(SRC)
    assert tmp.startswith(SRC + ".part-") and tmp.endswith(".flac")
    assert tmp != tmp_output_path(SRC)


def test_공통_인자():
    cmd = build_encode_cmd(SRC, "out.mp3", Target("MP3", 320), FLAC_24_96)
    assert cmd[1:6] == ["-hide_banner", "-nostdin", "-y", "-i", SRC]
    assert args_after(cmd, "-map") == "0:a:0", "첫 오디오 스트림만"
    assert args_after(cmd, "-map_metadata") == "0", "태그를 옮긴다"
    assert cmd.count("-map") == 1, "그림은 따로 붙인다"
    assert cmd[-1] == "out.mp3"


def test_MP3():
    cmd = build_encode_cmd(SRC, "o.mp3", Target("MP3", 320), FLAC_24_96)
    assert args_after(cmd, "-c:a") == "libmp3lame" and args_after(cmd, "-b:a") == "320k"
    assert args_after(cmd, "-id3v2_version") == "3"
    assert args_after(cmd, "-ar") == "48000", "96kHz 원본은 48kHz 로"


def test_M4A_와_OGG():
    cmd = build_encode_cmd(SRC, "o.m4a", Target("M4A", 256), MP3_128)
    assert args_after(cmd, "-c:a") == "aac" and args_after(cmd, "-b:a") == "256k"
    assert "-ar" not in cmd, "48kHz 이하 원본은 그대로"
    cmd = build_encode_cmd(SRC, "o.ogg", Target("OGG", 192), FLAC_24_96)
    assert args_after(cmd, "-c:a") == "libvorbis" and args_after(cmd, "-b:a") == "192k"
    assert args_after(cmd, "-ar") == "48000"


def test_OGG_품질_값으로_다시():
    cmd = build_encode_cmd(SRC, "o.ogg", Target("OGG", 320), MP3_128, vorbis_quality=True)
    assert args_after(cmd, "-q:a") == "9" and "-b:a" not in cmd
    assert vorbis_setup_failed("[libvorbis @ 0x1] encoder setup failed")
    assert not vorbis_setup_failed("[aac @ 0x1] something")


@pytest.mark.parametrize(("depth", "codec"), [(24, "pcm_s24le"), (16, "pcm_s16le")])
def test_WAV(depth, codec):
    cmd = build_encode_cmd(SRC, "o.wav", Target("WAV", bit_depth=depth, sample_rate=96000), FLAC_24_96)
    assert args_after(cmd, "-c:a") == codec and args_after(cmd, "-ar") == "96000"


def test_FLAC():
    cmd = build_encode_cmd(SRC, "o.flac", Target("FLAC", bit_depth=24, sample_rate=48000), FLAC_24_96)
    assert args_after(cmd, "-c:a") == "flac" and args_after(cmd, "-sample_fmt") == "s32"
    assert args_after(cmd, "-bits_per_raw_sample") == "24" and args_after(cmd, "-ar") == "48000"
    cmd = build_encode_cmd(SRC, "o.flac", Target("FLAC", bit_depth=16, sample_rate=44100), FLAC_24_96)
    assert args_after(cmd, "-sample_fmt") == "s16" and "-bits_per_raw_sample" not in cmd


def test_앨범_그림은_담을_수_있는_형식에만():
    assert all(wants_cover(FLAC_24_96, Target(f)) for f in ("MP3", "M4A", "FLAC"))
    assert not wants_cover(FLAC_24_96, Target("OGG")) and not wants_cover(FLAC_24_96, Target("WAV"))
    assert not wants_cover(MP3_128, Target("MP3"))


def test_앨범_그림_붙이기():
    cmd = build_cover_cmd("a.part.mp3", SRC, "o.part.mp3", Target("MP3"))
    assert cmd[cmd.index("-i") + 1] == "a.part.mp3" and cmd[cmd.index("-i", cmd.index("-i") + 1) + 1] == SRC
    assert args_after(cmd, "-c") == "copy" and args_after(cmd, "-disposition:v:0") == "attached_pic"
    assert "1:v:0" in cmd and "-id3v2_version" in cmd and cmd[-1] == "o.part.mp3"
    assert "-id3v2_version" not in build_cover_cmd("a", SRC, "o.flac", Target("FLAC"))


def test_실패_사유_요약():
    err = "ffmpeg version 8.1\nbuilt with gcc\nconfiguration: --x\nlibavutil 60\n" + \
        "\n".join(f"line {i}" for i in range(40)) + "\nsize=1kB time=00:00:01.00 bitrate=1k\n"
    s = summarize_stderr(err)
    assert "ffmpeg version" not in s and "line 0" in s and "..." in s and len(s.splitlines()) == 20
    assert summarize_stderr("") == "(stderr 없음)"
    assert last_error_line(err) == "line 39"


def test_자동_이름은_결과의_실제_음질로():
    """변환이면 목표 음질, 복사면 원본 음질. 1.x 는 복사한 파일에도 목표 음질을 붙였다."""
    _a, dest, _s = plan_output(SRC, FLAC_24_96, Target("MP3", 192), "", "suffix", None)
    assert dest.endswith("01 곡_192k.mp3")
    cd = AudioInfo("flac", 44100, 0, 16)
    _a, dest, _s = plan_output(SRC, cd, Target("WAV", bit_depth=24, sample_rate=96000), "", "suffix", None)
    assert dest.endswith("01 곡_16bit_44.1k.wav"), "형식이 다르면 원본 음질로 변환한다"
    _a, dest, _s = plan_output(SRC, cd, Target("FLAC", bit_depth=24, sample_rate=96000), "", "suffix", None)
    assert dest.endswith("01 곡_16bit_44.1k.flac"), "같은 형식이면 복사, 이름은 원본 음질"
    _a, dest, _s = plan_output(SRC.replace(".flac", ".mp3"), MP3_128, Target("MP3", 320), "", "prefix", None)
    assert dest.endswith("[128k]_01 곡.mp3")
    _a, dest, _s = plan_output(SRC.replace(".flac", ".m4a"), AudioInfo("aac", 44100), Target("FLAC"), "", "suffix", None)
    assert dest.endswith("01 곡_aac.m4a"), "비트레이트를 모르면 코덱 이름"
    _a, dest, same = plan_output(SRC, FLAC_24_96, Target("FLAC", bit_depth=16), "", "overwrite", None)
    assert dest == SRC and same
