"""파일 하나: 분석 → 변환할지 판단 → 변환 또는 복사(임시 파일에) → 확인 → 제 이름으로 바꿈.

결과는 늘 `<결과>.part-...` 임시 파일에 먼저 만든다. 다 만들고 확인한 뒤에만 제 이름으로 바꾸므로
덮어쓰기(입력과 출력이 같은 경로)도 된다. 1.x 는 같은 경로에 바로 써서 FFmpeg 가 거절했다.
"""

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from ..config import EXTENSIONS
from . import leftovers
from .decide import Target, auto_value, decide, effective, source_affix, source_spec
from .errorlog import log_conversion_error
from .ffmpeg_cmd import (
    build_cover_cmd,
    build_encode_cmd,
    last_error_line,
    resolve_output_path,
    safe_remove,
    same_path,
    tmp_is_valid,
    tmp_output_path,
    vorbis_setup_failed,
    wants_cover,
)
from .probe import AudioInfo, probe
from .runner import run_ffmpeg_and_track

Status = Literal["done", "copied", "skipped", "failed", "cancelled"]
Progress = Callable[[float, str, str], None]  # (퍼센트 0~100, time=, speed=)


@dataclass
class Result:
    status: Status
    message: str
    output: str | None = None


def plan_output(src: str, info: AudioInfo, target: Target, out_dir: str, name_mode: str, value: str | None
                ) -> tuple[str, str, bool]:
    """(동작 encode|copy, 결과 경로, 원본과 같은 경로인지)

    value 가 None 이면 이름에 붙일 문구를 결과의 실제 음질로 정한다: 변환이면 목표(_192k), 복사면 원본(_16bit_44.1k).
    """
    action = decide(info, target)
    # 복사는 원본 형식을 그대로 두므로 확장자도 원본 것이다
    ext = EXTENSIONS[target.format] if action == "encode" else os.path.splitext(src)[1]
    if value is None:
        value = auto_value(name_mode, effective(info, target).affix if action == "encode" else source_affix(info))
    dest = resolve_output_path(src, out_dir, name_mode, value, ext)
    return action, dest, same_path(src, dest)


def convert(src: str, target: Target, out_dir: str = "", name_mode: str = "suffix", value: str | None = None,
            progress: Progress | None = None, cancel: threading.Event | None = None,
            probe_fn: Callable[[str], AudioInfo | None] = probe) -> Result:
    if not os.path.isfile(src):
        return Result("failed", "파일이 없습니다.")
    info = probe_fn(src)
    if info is None:
        return Result("failed", "오디오 정보를 읽지 못했습니다. 손상됐거나 오디오가 아닌 파일입니다.")

    action, dest, same = plan_output(src, info, target, out_dir, name_mode, value)
    if action == "encode":
        target = effective(info, target)  # 원본보다 높이지 않은 실제 음질로 만들고 알린다
    src_spec = f"{info.label} {source_spec(info)}"
    if action == "copy" and same:
        return Result("skipped", f"변환할 필요 없음: 원본 {src_spec}이(가) 목표 {target.label}보다 낮거나 같습니다.", dest)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = tmp_output_path(dest)
    # 앨범 그림을 붙일 때는 소리를 먼저 다른 임시 파일에 만든다
    audio = tmp_output_path(dest) if action == "encode" and wants_cover(info, target) else tmp
    parts = [tmp] if audio == tmp else [tmp, audio]
    for p in parts:
        leftovers.remember(p)  # 앱이 강제로 끝나 지우지 못하면 다음 시작 때 지운다
    note = ""

    def cleanup() -> None:
        for p in parts:
            safe_remove(p)

    try:
        if action == "copy":
            shutil.copy2(src, tmp)
        else:
            def run(vorbis_quality: bool = False) -> tuple[int, str]:
                cmd = build_encode_cmd(src, audio, target, info, vorbis_quality)
                return run_ffmpeg_and_track(cmd, info.duration, progress, cancel, audio)

            rc, err = run()
            if rc not in (0, -1) and target.format == "OGG" and vorbis_setup_failed(err):
                safe_remove(audio)
                rc, err = run(vorbis_quality=True)
            if (cancel is not None and cancel.is_set()) or err == "USER_CANCELLED":
                cleanup()
                return Result("cancelled", "중단했습니다.")
            if err.startswith("STUCK_TIMEOUT"):
                cleanup()
                log_conversion_error(os.path.basename(src), rc, err[len("STUCK_TIMEOUT"):], " (진행 없음으로 강제 종료)")
                return Result("failed", "FFmpeg가 오래 진행하지 않아 끝냈습니다.")
            if rc != 0:
                cleanup()
                log_conversion_error(os.path.basename(src), rc, err)
                line = last_error_line(err)
                return Result("failed", f"FFmpeg 오류 (코드 {rc})" + (f": {line}" if line else ""))
            if audio != tmp:
                rc, err = run_ffmpeg_and_track(build_cover_cmd(audio, src, tmp, target), 0, None, cancel, tmp)
                if (cancel is not None and cancel.is_set()) or err == "USER_CANCELLED":
                    cleanup()
                    return Result("cancelled", "중단했습니다.")
                if rc == 0 and tmp_is_valid(tmp):
                    safe_remove(audio)
                else:
                    # 그림이 그 형식에 맞지 않는 등. 소리는 이미 다 만들었으니 그림 없이 낸다
                    log_conversion_error(os.path.basename(src), rc, err, " (앨범 그림 붙이기)")
                    safe_remove(tmp)
                    os.replace(audio, tmp)
                    note = " (앨범 그림은 넣지 못함)"

        if not tmp_is_valid(tmp):
            cleanup()
            return Result("failed", "결과 파일이 비어 있습니다.")
        os.replace(tmp, dest)  # 덮어쓰기면 여기서 원본이 바뀐다. 결과를 확인한 뒤라 안전하다
    except OSError as exc:
        cleanup()
        return Result("failed", f"파일을 쓰지 못했습니다: {exc}")
    finally:
        for p in parts:
            if not os.path.exists(p):
                leftovers.forget(p)

    if action == "copy":
        return Result("copied", f"원본 그대로 복사: 원본 {src_spec}이(가) 목표 {target.label}보다 낮거나 같습니다.", dest)
    if name_mode == "overwrite" and not same:
        note += " (형식이 달라 원본은 그대로 둠)"
    return Result("done", f"{src_spec} → {target.label}{note}", dest)
