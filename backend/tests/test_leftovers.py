"""만들다 만 임시 결과 파일 기록과 다음 시작 때의 정리."""

import os

import pytest

from audioconverter.core import leftovers
from audioconverter.core.ffmpeg_cmd import tmp_output_path

DEAD_PID = 4_000_000  # 이런 pid 의 프로세스는 없다


def part(tmp_path, pid=DEAD_PID, name="song", ext=".flac"):
    p = tmp_path / f"{name}{ext}.part-{pid}-0123abcd{ext}"
    p.write_bytes(b"half")
    return str(p)


def test_기록했다가_지우면_남는_것이_없다(tmp_path):
    p = part(tmp_path)
    leftovers.remember(p)
    assert leftovers._read() == [p]
    leftovers.forget(p)
    assert leftovers._read() == []
    assert not leftovers._file().exists()


@pytest.mark.parametrize("ext", [".mp3", ".m4a", ".ogg", ".flac", ".wav", ".dsf"])
def test_끝난_실행이_남긴_임시_파일을_지운다(tmp_path, ext):
    p = part(tmp_path, ext=ext)
    leftovers.remember(p)
    assert leftovers.clean() == 1
    assert not os.path.exists(p)
    assert leftovers._read() == []


def test_임시_파일_이름은_정리_대상_모양이다(tmp_path):
    tmp = tmp_output_path(str(tmp_path / "곡.mp3"))
    assert tmp.endswith(".mp3") and leftovers.PART_RE.search(tmp)


def test_살아_있는_실행의_임시_파일은_남긴다(tmp_path):
    p = part(tmp_path, pid=os.getpid())
    leftovers.remember(p)
    assert leftovers.clean() == 0
    assert os.path.exists(p) and leftovers._read() == [p]


def test_임시_파일_이름이_아니면_지우지_않는다(tmp_path):
    keep = tmp_path / "song.flac"
    keep.write_bytes(b"real")
    leftovers.remember(str(keep))
    assert leftovers.clean() == 0
    assert keep.exists() and leftovers._read() == []
