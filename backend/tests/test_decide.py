"""변환할지 복사할지(PLAN.md 의 표)와 규격 문구."""

import pytest

from audioconverter.core.decide import Target, decide, khz, source_spec
from audioconverter.core.probe import AudioInfo, parse

FLAC_24_96 = AudioInfo("flac", 96000, 0, 24)
FLAC_16_44 = AudioInfo("flac", 44100, 0, 16)
WAV_16_44 = AudioInfo("pcm_s16le", 44100, 1_411_200, 16)
DSD64 = AudioInfo("dsd_lsbf_planar", 2_822_400, 0, 1)
MP3_320 = AudioInfo("mp3", 44100, 320_000)
MP3_128 = AudioInfo("mp3", 44100, 128_000)
AAC_UNKNOWN = AudioInfo("aac", 44100, 0)


@pytest.mark.parametrize(("info", "target", "action"), [
    # DSD 는 늘 변환한다
    (DSD64, Target("FLAC", bit_depth=24, sample_rate=192000), "encode"),
    (DSD64, Target("MP3", 320), "encode"),
    # 무손실 → 손실: 변환
    (FLAC_16_44, Target("MP3", 320), "encode"),
    (WAV_16_44, Target("OGG", 128), "encode"),
    # 무손실 → 무손실: 목표가 낮을 때만 변환
    (FLAC_24_96, Target("FLAC", bit_depth=16, sample_rate=44100), "encode"),
    (FLAC_24_96, Target("WAV", bit_depth=24, sample_rate=48000), "encode"),
    (FLAC_24_96, Target("WAV", bit_depth=24, sample_rate=96000), "copy"),
    (FLAC_16_44, Target("FLAC", bit_depth=24, sample_rate=96000), "copy"),
    (FLAC_16_44, Target("WAV", bit_depth=16, sample_rate=44100), "copy"),
    # 손실 → 무손실: 복사(음질을 높일 수 없다)
    (MP3_320, Target("FLAC", bit_depth=24, sample_rate=192000), "copy"),
    # 손실 → 손실: 목표 비트레이트가 낮을 때만 변환
    (MP3_320, Target("MP3", 192), "encode"),
    (MP3_320, Target("M4A", 256), "encode"),
    (MP3_128, Target("MP3", 128), "copy"),
    (MP3_128, Target("OGG", 320), "copy"),
    # 원본 비트레이트를 모르면 변환
    (AAC_UNKNOWN, Target("M4A", 320), "encode"),
])
def test_판단표(info, target, action):
    assert decide(info, target) == action


def test_목표_문구():
    assert Target("MP3", 192).label == "MP3 192k"
    assert Target("FLAC", bit_depth=24, sample_rate=96000).label == "FLAC 24bit/96k"
    assert Target("WAV", bit_depth=16, sample_rate=44100).spec == "16bit/44.1k"
    assert Target("FLAC", bit_depth=16, sample_rate=44100).affix == "16bit_44.1k"
    assert Target("OGG", 128).affix == "128k"
    assert khz(48000) == "48" and khz(192000) == "192" and khz(22050) == "22.05"


def test_원본_문구():
    assert source_spec(FLAC_24_96) == "24bit/96k"
    assert source_spec(MP3_320) == "320k"
    assert source_spec(AAC_UNKNOWN) == "?k"
    assert source_spec(DSD64) == "DSD64"
    assert AudioInfo("dsd_msbf", 5_644_800).label == "DSD128"
    assert AudioInfo("dsd_msbf", 11_289_600).label == "DSD256"


def test_무손실_코덱():
    for codec in ("flac", "alac", "ape", "pcm_s24le", "pcm_f32le", "dsd_lsbf", "wavpack", "tta"):
        assert AudioInfo(codec).lossless, codec
    for codec in ("mp3", "aac", "vorbis", "opus"):
        assert not AudioInfo(codec).lossless, codec


def test_ffprobe_결과_읽기():
    data = {
        "streams": [
            {"codec_type": "audio", "codec_name": "FLAC", "sample_rate": "96000", "bits_per_raw_sample": "24",
             "sample_fmt": "s32", "channels": 2, "disposition": {"attached_pic": 0}},
            {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}},
        ],
        "format": {"duration": "183.5"},
    }
    info = parse(data)
    assert info == AudioInfo("flac", 96000, 0, 24, 2, 183.5, True)


def test_ffprobe_비트_깊이는_샘플_형식으로도_안다():
    def depth(**s):
        return parse({"streams": [{"codec_type": "audio", "codec_name": "x", **s}]}).bit_depth

    assert depth(bits_per_raw_sample="0", sample_fmt="s32p") == 24
    assert depth(sample_fmt="fltp") == 24
    assert depth(sample_fmt="s16") == 16
    assert depth() == 16


def test_ffprobe_오디오가_없으면_None():
    assert parse({"streams": [{"codec_type": "video"}]}) is None
    assert parse({}) is None


def test_ffprobe_비트레이트는_스트림_값만_본다():
    """파일 전체 비트레이트에는 앨범 그림이 더해져 있어 쓰지 않는다."""
    info = parse({"streams": [{"codec_type": "audio", "codec_name": "mp3", "sample_rate": "44100"}],
                  "format": {"bit_rate": "999000", "duration": "N/A"}})
    assert info.bit_rate == 0 and info.duration == 0.0


def test_원본_형식_이름():
    assert AudioInfo("pcm_s24le").label == "WAV"
    assert AudioInfo("vorbis").label == "OGG"
    assert AudioInfo("aac").label == "AAC"
