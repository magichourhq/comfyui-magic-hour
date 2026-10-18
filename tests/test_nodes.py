import os
import sys
import types
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
pkg = __import__("comfyui-magic-hour".replace("-", "_") if False else os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), fromlist=["x"])
h = sys.modules[pkg.__name__ + ".helpers"]
nodes = sys.modules[pkg.__name__ + ".nodes"]


class FakeTensor:
    def __init__(self, arr):
        self.arr = arr

    def __getitem__(self, i):
        return FakeTensor(self.arr[i])

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.arr


class FakeVideo:
    def save_to(self, path):
        open(path, "wb").write(b"fakemp4")

    def get_duration(self):
        return 8.0


class FakeResource:
    def __init__(self, calls, status="complete"):
        self.calls, self.status = calls, status

    def generate(self, **kw):
        self.calls.append(kw)
        # inputs must exist on disk at call time
        for k, v in kw["assets"].items():
            if k.endswith("_file_path"):
                assert os.path.exists(v), v
        out = os.path.join(kw["download_directory"], "out.mp4")
        open(out, "wb").write(b"x")
        err = types.SimpleNamespace(message="boom")
        return types.SimpleNamespace(
            status=self.status, error=err, downloaded_paths=[out], credits_charged=240
        )


def fake_client(calls, status="complete"):
    v1 = types.SimpleNamespace(
        image_to_video=FakeResource(calls, status),
        ai_talking_photo=FakeResource(calls, status),
        face_swap=FakeResource(calls, status),
        character_replace=FakeResource(calls, status),
    )
    return types.SimpleNamespace(v1=v1)


class T(unittest.TestCase):
    def setUp(self):
        self.calls = []
        h.make_client = lambda: fake_client(self.calls)
        h.to_comfy_video = lambda p: ("VIDEO", p)
        self.img = FakeTensor(np.random.rand(1, 16, 16, 3).astype("float32"))
        self.audio = {"waveform": FakeTensor(np.zeros((1, 2, 32000), dtype="float32")), "sample_rate": 16000}

    def test_missing_key(self):
        os.environ.pop("MAGIC_HOUR_API_KEY", None)
        if os.path.exists(h.KEY_FILE):
            self.skipTest("api_key.txt present")
        with self.assertRaises(RuntimeError):
            h.get_api_key()

    def test_i2v(self):
        out = nodes.MagicHourImageToVideo().run(self.img, 5.0, "kling-3.0", "720p", "a dog runs")
        kw = self.calls[0]
        self.assertEqual(kw["model"], "kling-3.0")
        self.assertEqual(kw["style"], {"prompt": "a dog runs"})
        self.assertEqual(out[2], 240)

    def test_i2v_default_model_omitted(self):
        nodes.MagicHourImageToVideo().run(self.img, 5.0, "default", "720p", "")
        self.assertNotIn("model", self.calls[0])
        self.assertNotIn("style", self.calls[0])

    def test_talking_auto_window(self):
        nodes.MagicHourTalkingPhoto().run(self.img, self.audio, "realistic", 0.0, 0.0, "")
        self.assertEqual((self.calls[0]["start_seconds"], self.calls[0]["end_seconds"]), (0.0, 2.0))

    def test_face_swap_window(self):
        nodes.MagicHourFaceSwap().run(FakeVideo(), self.img, "default", 1.0, 0.0)
        kw = self.calls[0]
        self.assertEqual((kw["start_seconds"], kw["end_seconds"]), (1.0, 8.0))
        self.assertEqual(kw["assets"]["face_swap_mode"], "all-faces")

    def test_character_replace_bad_resolution(self):
        with self.assertRaises(ValueError):
            nodes.MagicHourCharacterReplace().run(FakeVideo(), self.img, "replace", "wan-animate", "1080p", 0, 0)

    def test_character_replace_ok(self):
        nodes.MagicHourCharacterReplace().run(FakeVideo(), self.img, "animate", "kling-3.0", "1080p", 0, 5)
        self.assertEqual(self.calls[0]["style"], {"mode": "animate"})

    def test_failed_job_raises(self):
        h.make_client = lambda: fake_client(self.calls, status="error")
        with self.assertRaises(RuntimeError) as cm:
            nodes.MagicHourImageToVideo().run(self.img, 5.0, "default", "720p", "")
        self.assertIn("boom", str(cm.exception))

    def test_wav_roundtrip(self):
        path, secs = h.audio_to_wav(self.audio)
        with wave.open(path) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (2, 16000))
        self.assertAlmostEqual(secs, 2.0)
        os.remove(path)

    def test_api_error_is_readable(self):
        class Resp:
            status_code = 402
            text = ""
            def json(self):
                return {"code": "plan_upgrade_required", "message": "Resolution 720p is not available"}
        class Boom(Exception):
            response = Resp()
        def fn(**kw):
            raise Boom("raw")
        with self.assertRaises(RuntimeError) as cm:
            h.call(fn)
        self.assertIn("402", str(cm.exception))
        self.assertIn("not available", str(cm.exception))
        self.assertIn("paid plan", str(cm.exception))

    def test_non_api_error_passes_through(self):
        def fn(**kw):
            raise KeyError("x")
        with self.assertRaises(KeyError):
            h.call(fn)

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            h.resolve_window(5, 3, None)


if __name__ == "__main__":
    unittest.main()
