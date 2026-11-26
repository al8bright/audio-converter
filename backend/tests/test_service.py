"""Service: 대기열·분석·일괄 변환·중단·설정. FFmpeg 대신 FakeConvert 를 쓴다."""

import os
import threading

import pytest
from conftest import Result, Settings, audio, run_now

from audioconverter.config import SettingsStore
from audioconverter.core.decide import Target
from audioconverter.core.probe import AudioInfo
from audioconverter.core.service import Service, ServiceError


def statuses(svc):
    return {i["name"]: i["status"] for i in svc.snapshot()["items"]}


class TestAdd:
    def test_폴더는_하위까지_오디오만_담고_정보를_읽는다(self, svc, tmp_path):
        audio(tmp_path / "in", "a.flac")
        audio(tmp_path / "in" / "sub", "b.MP3")
        audio(tmp_path / "in", "cover.jpg")
        r = svc.add_paths([str(tmp_path / "in")])
        assert (r["added"], r["skipped"], r["message"]) == (2, 1, None)
        items = svc.snapshot()["items"]
        assert [i["name"] for i in items] == ["a.flac", "b.MP3"]
        assert all(i["status"] == "waiting" and i["source"] == "FLAC 24bit/96k" and i["size"] == 100 for i in items)
        assert items[0]["duration"] == 180.0 and items[0]["info"]["sample_rate"] == 96000

    def test_같은_파일은_한_번만_담는다(self, svc, tmp_path):
        p = audio(tmp_path, "a.flac")
        svc.add_paths([p])
        r = svc.add_paths([p.upper(), p.replace("\\", "/")] if os.name == "nt" else [p])
        assert r["added"] == 0 and "이미 대기열" in r["message"]
        assert len(svc.items) == 1

    def test_오디오가_없으면_알린다(self, svc, tmp_path):
        with pytest.raises(ServiceError, match="추가할 오디오 파일이 없습니다"):
            svc.add_paths([audio(tmp_path, "a.txt"), str(tmp_path / "없는파일.flac")])

    def test_정보를_못_읽으면_실패로_두고_변환하지_않는다(self, svc, tmp_path, probes):
        probes["broken.flac"] = None
        svc.add_paths([audio(tmp_path, "broken.flac")])
        item = svc.snapshot()["items"][0]
        assert item["status"] == "failed" and "오디오 정보를 읽지 못했습니다" in item["message"]
        assert item["plan"] is None
        with pytest.raises(ServiceError, match="변환할 파일이 없습니다"):
            svc.start(None)

    def test_지운_항목의_분석_결과는_버린다(self, make_svc, tmp_path):
        later = []
        svc = make_svc(spawn=lambda fn, *a: later.append((fn, a)))
        svc.add_paths([audio(tmp_path, "a.flac")])
        svc.clear()
        fn, a = later.pop()
        fn(*a)
        assert svc.items == []


class TestPlan:
    def plans(self, svc):
        return {i["name"]: i["plan"] for i in svc.snapshot()["items"]}

    def test_예정_동작과_만들_파일_이름은_지금_설정을_따른다(self, svc, probes, tmp_path):
        probes["hi.flac"] = AudioInfo("flac", 96000, 0, 24)
        probes["cd.flac"] = AudioInfo("flac", 44100, 0, 16)
        probes["lo.mp3"] = AudioInfo("mp3", 44100, 128_000)
        svc.add_paths([audio(tmp_path, n) for n in ("hi.flac", "cd.flac", "lo.mp3")])
        p = self.plans(svc)
        assert {n: x["action"] for n, x in p.items()} == {"hi.flac": "encode", "cd.flac": "encode", "lo.mp3": "copy"}
        assert p["hi.flac"]["output"] == "hi_192k.mp3"
        assert p["lo.mp3"]["output"] == "lo_128k.mp3", "복사한 파일은 원본 음질로 이름을 붙인다"
        assert svc.snapshot()["target"] == "MP3 192k"

        svc.update_settings({"format": "FLAC", "bit_depth": 16, "sample_rate": 44100})
        p = self.plans(svc)
        assert {n: x["action"] for n, x in p.items()} == {"hi.flac": "encode", "cd.flac": "copy", "lo.mp3": "copy"}
        assert (p["hi.flac"]["output"], p["cd.flac"]["output"]) == ("hi_16bit_44.1k.flac", "cd_16bit_44.1k.flac")

        svc.update_settings({"name_mode": "prefix", "name_text": "작게_"})
        assert self.plans(svc)["hi.flac"]["output"] == "작게_hi.flac"

    def test_덮어쓰기(self, svc, probes, tmp_path):
        probes["cd.flac"] = AudioInfo("flac", 44100, 0, 16)
        svc.add_paths([audio(tmp_path, n) for n in ("hi.flac", "cd.flac")])
        svc.update_settings({"name_mode": "overwrite", "format": "FLAC"})
        p = self.plans(svc)
        assert (p["hi.flac"]["action"], p["hi.flac"]["output"], p["hi.flac"]["keeps_source"]) == (
            "encode", "hi.flac", False)
        assert p["cd.flac"]["action"] == "skip", "원본보다 높일 수 없고 같은 자리라 둔다"
        svc.update_settings({"format": "MP3"})
        assert self.plans(svc)["hi.flac"]["keeps_source"] is True, "형식이 달라 원본이 남는다"


class TestBatch:
    def test_결과별_상태와_집계(self, svc, convert, tmp_path):
        names = ["ok.flac", "copy.mp3", "same.flac", "bad.flac"]
        svc.add_paths([audio(tmp_path, n) for n in names])
        convert.results.update({
            "copy.mp3": Result("copied", "원본 그대로 복사", str(tmp_path / "copy_128k.mp3")),
            "same.flac": Result("skipped", "변환할 필요 없음", str(tmp_path / "same.flac")),
            "bad.flac": Result("failed", "FFmpeg 오류 (코드 1)"),
        })
        assert svc.start(None)["count"] == 4
        snap = svc.snapshot()
        items = {i["name"]: i for i in snap["items"]}
        assert {n: i["status"] for n, i in items.items()} == {
            "ok.flac": "done", "copy.mp3": "copied", "same.flac": "skipped", "bad.flac": "failed"}
        assert items["bad.flac"]["message"] == "FFmpeg 오류 (코드 1)" and items["bad.flac"]["output"] is None
        assert items["ok.flac"]["output"] == str(tmp_path / "ok_192k.mp3") and items["ok.flac"]["percent"] == 1.0
        b = snap["batch"]
        assert not b["running"] and b["overall"] == 1.0
        assert b["result"]["message"] == "4개 중 3개 완료, 복사 1개, 실패 1개"
        assert (b["result"]["done"], b["result"]["copied"], b["result"]["skipped"]) == (1, 1, 1)

    def test_설정이_변환에_전달된다(self, svc, store, convert, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        store.save(Settings(save_mode="folder", save_dir=str(out), format="WAV", bit_depth=24, sample_rate=96000,
                            name_mode="prefix", name_text="hi_"))
        svc.add_paths([audio(tmp_path, "a.flac")])
        svc.start(None)
        call = convert.calls[0]
        assert call["target"] == Target("WAV", 192, 24, 96000)
        assert (call["out_dir"], call["name_mode"], call["value"]) == (str(out), "prefix", "hi_")

    def test_이름_문구를_비우면_자동(self, svc, convert, tmp_path):
        svc.add_paths([audio(tmp_path, "a.flac")])
        svc.start(None)
        assert convert.calls[0]["value"] is None

    def test_동시_작업_수는_권장값이고_항목_수를_넘지_않는다(self, make_svc, store, tmp_path):
        svc = make_svc(recommended=4)
        svc.add_paths([audio(tmp_path, f"{n}.flac") for n in "ab"])
        assert svc.start(None)["jobs"] == 2
        store.save(Settings(jobs=1))
        svc.add_paths([audio(tmp_path, f"{n}.flac") for n in "cd"])
        assert svc.start(None)["jobs"] == 1

    def test_실패와_중단은_다시_변환하고_완료는_건너뛴다(self, svc, convert, tmp_path):
        svc.add_paths([audio(tmp_path, n) for n in ("ok.flac", "bad.flac")])
        convert.results["bad.flac"] = Result("failed", "x")
        svc.start(None)
        del convert.results["bad.flac"]
        convert.calls.clear()
        svc.start(None)
        assert [os.path.basename(c["path"]) for c in convert.calls] == ["bad.flac"]
        assert statuses(svc) == {"ok.flac": "done", "bad.flac": "done"}

    def test_골라서_변환한다(self, svc, tmp_path):
        svc.add_paths([audio(tmp_path, n) for n in ("a.flac", "b.flac")])
        svc.start([svc.items[1].id])
        assert statuses(svc) == {"a.flac": "waiting", "b.flac": "done"}

    def test_한_항목의_예외가_나머지를_막지_않는다(self, svc, convert, tmp_path):
        svc.add_paths([audio(tmp_path, n) for n in ("boom.flac", "ok.flac")])
        convert.results["boom.flac"] = RuntimeError("터짐")
        svc.start(None)
        items = {i["name"]: i for i in svc.snapshot()["items"]}
        assert items["boom.flac"]["status"] == "failed" and "터짐" in items["boom.flac"]["message"]
        assert items["ok.flac"]["status"] == "done"
        assert not svc.batch.running

    @pytest.mark.parametrize("setup, message", [
        ("empty", "변환할 파일이 없습니다"),
        ("analyzing", "오디오 정보를 읽는 중"),
        ("no_dir", "저장 폴더를 지정해 주세요"),
        ("gone_dir", "저장 폴더를 찾을 수 없어"),
        ("no_ffmpeg", "FFmpeg를 찾을 수 없습니다"),
    ])
    def test_시작할_수_없으면_이유를_알린다(self, make_svc, store, tmp_path, monkeypatch, setup, message):
        svc = make_svc(spawn=(lambda fn, *a: None) if setup == "analyzing" else run_now)
        if setup != "empty":
            svc.add_paths([audio(tmp_path, "a.flac")])
        if setup == "no_dir":
            store.save(Settings(save_mode="folder"))
        if setup == "gone_dir":
            store.save(Settings(save_mode="folder", save_dir=str(tmp_path / "gone")))
        if setup == "no_ffmpeg":
            monkeypatch.setenv("AUDIOCONVERTER_TOOLS_DIR", str(tmp_path / "nothing"))
            monkeypatch.setenv("PATH", "")
        with pytest.raises(ServiceError, match=message):
            svc.start(None)
        assert not svc.batch.running


class TestStop:
    def test_중단하면_변환_중인_것은_중단_나머지는_대기로_남는다(self, make_svc, convert, killed, tmp_path):
        threads = []

        def spawn(fn, *a):
            t = threading.Thread(target=fn, args=a)
            threads.append(t)
            t.start()

        started = threading.Event()

        def slow(progress, cancel):
            started.set()
            assert cancel.wait(5), "중단 신호가 오지 않았다"
            return Result("cancelled", "중단했습니다.")

        svc = make_svc(spawn=spawn)
        svc.add_paths([audio(tmp_path, n) for n in ("a.flac", "b.flac", "c.flac")])
        for t in threads:
            t.join(5)  # 분석
        svc.settings.save(Settings(jobs=1))
        convert.results["a.flac"] = slow
        svc.start(None)
        assert started.wait(5)
        assert svc.stop() is True
        for t in threads:
            t.join(5)
        assert killed, "실행 중인 ffmpeg 를 바로 끊는다"
        assert statuses(svc) == {"a.flac": "stopped", "b.flac": "waiting", "c.flac": "waiting"}
        result = svc.snapshot()["batch"]["result"]
        assert result["stopped"] == 3 and result["message"] == "3개 중 0개 완료, 중단 3개"
        assert not svc.batch.running and not svc.stop()

    def test_변환_중에는_대기열과_변환_설정을_바꾸지_못한다(self, make_svc, tmp_path):
        later = []
        svc = make_svc(spawn=lambda fn, *a: later.append((fn, a)))
        svc.add_paths([audio(tmp_path, "a.flac")])
        fn, a = later.pop()
        fn(*a)  # 분석
        svc.start(None)  # 변환 작업은 later 에 남겨 둔다
        for call in (lambda: svc.remove(svc.items[0].id), svc.clear, svc.clear_finished,
                     lambda: svc.update_settings({"format": "OGG"}), lambda: svc.start(None)):
            with pytest.raises(ServiceError) as e:
                call()
            assert e.value.status == 409
        svc.update_settings({"sidebar": "closed"})  # 화면 설정은 바꿀 수 있다
        r = svc.add_paths([audio(tmp_path, "b.flac")])
        assert "이번 변환에는 포함되지 않습니다" in r["message"]
        fn, a = later.pop(0)
        fn(*a)
        assert any("포함되지 않았습니다" in n["text"] for n in svc.snapshot()["notices"])


class TestSettings:
    def test_저장되고_다시_읽힌다(self, svc, store):
        svc.update_settings({"jobs": 3, "format": "OGG", "bitrate": 320, "name_text": "_hq"})
        again = SettingsStore(store.path).get()
        assert (again.jobs, again.format, again.bitrate, again.name_text) == (3, "OGG", 320, "_hq")
        svc.update_settings({"jobs": None})
        assert store.get().jobs is None

    def test_기본값(self):
        s = Settings()
        assert (s.format, s.bitrate, s.bit_depth, s.sample_rate, s.name_mode, s.name_text) == (
            "MP3", 192, 16, 44100, "suffix", "")

    def test_없는_폴더와_파일_이름에_못_쓰는_문자는_거절한다(self, svc, tmp_path):
        with pytest.raises(ServiceError, match="폴더를 찾을 수 없습니다"):
            svc.update_settings({"save_dir": str(tmp_path / "gone")})
        with pytest.raises(ServiceError, match="문구"):
            svc.update_settings({"name_text": "a/b"})
        with pytest.raises(ServiceError):
            svc.update_settings({"bitrate": 160})
        svc.update_settings({"save_dir": str(tmp_path)})
        assert svc.settings.get().save_dir == str(tmp_path)

    def test_망가진_설정_파일은_기본값으로_읽는다(self, tmp_path):
        p = tmp_path / "s.json"
        p.write_text("{ broken", encoding="utf-8")
        assert SettingsStore(p).get() == Settings()


class TestQueue:
    def test_완료_항목만_비운다(self, svc, convert, tmp_path):
        svc.add_paths([audio(tmp_path, n) for n in ("ok.flac", "bad.flac")])
        convert.results["bad.flac"] = Result("failed", "x")
        svc.start(None)
        assert svc.clear_finished() == 1
        assert statuses(svc) == {"bad.flac": "failed"}
        with pytest.raises(ServiceError):
            svc.clear_finished()

    def test_열기는_대기열의_파일만(self, svc, tmp_path):
        svc.add_paths([audio(tmp_path, "a.flac")])
        item = svc.items[0]
        assert svc.open_target(item.id, folder=False) == item.path
        assert svc.open_target(item.id, folder=True) == str(tmp_path)
        with pytest.raises(ServiceError):
            svc.open_target("nope", folder=False)
        os.remove(item.path)
        with pytest.raises(ServiceError, match="찾을 수 없습니다"):
            svc.open_target(item.id, folder=False)

    def test_변환_중_전체_진행률(self, svc, tmp_path):
        svc.add_paths([audio(tmp_path, n) for n in ("a.flac", "b.flac")])
        svc.batch.total, svc.batch.finished = 2, 1
        svc.items[1].status, svc.items[1].percent = "converting", 0.5
        assert svc.snapshot()["batch"]["overall"] == 0.75


def test_hardware_는_한_번만_알아본다(store, convert):
    calls = []
    svc = Service(settings=store, convert=convert, detect=lambda: calls.append(1) or {"recommended_jobs": 1})
    svc.hardware()
    svc.hardware()
    assert calls == [1]


def test_권장_동시_작업_수는_4개_코어가_적으면_코어_수(monkeypatch):
    from audioconverter import config

    monkeypatch.setattr(config.os, "cpu_count", lambda: 16)
    assert config.recommended_jobs() == 4
    monkeypatch.setattr(config.os, "cpu_count", lambda: 2)
    assert config.recommended_jobs() == 2
    monkeypatch.setattr(config.os, "cpu_count", lambda: None)
    assert config.recommended_jobs() == 1
