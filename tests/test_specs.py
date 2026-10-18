"""Checks every spec-driven node against the REAL magic-hour SDK signatures.

No network, no credits: a fake client records the kwargs each node would send,
and we validate them against inspect.signature() and the SDK's TypedDicts.
"""
import inspect
import os
import sys
import types
import typing
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PKG = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pkg = __import__(PKG, fromlist=["x"])
h = sys.modules[PKG + ".helpers"]
more = sys.modules[PKG + ".nodes_more"]
generic = sys.modules[PKG + ".generic"]

from magic_hour import Client  # noqa: E402
from magic_hour.types import params  # noqa: E402

REAL = Client(token="test").v1

# Voice nodes are opt-in at runtime; register them here so they get validated too.
ALL_SPECS = list(more.SPECS) + [s for s in more.VOICE_SPECS if s not in more.SPECS]
for _s in ALL_SPECS:
    more.NODE_CLASS_MAPPINGS.setdefault(_s.key, generic.make_node(_s))


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
        open(path, "wb").write(b"mp4")

    def get_duration(self):
        return 8.0


def sample(decl):
    kind, cfg = (decl + ({},))[:2] if len(decl) == 1 else decl
    if isinstance(kind, list):
        return cfg.get("default", kind[0])
    if kind == "IMAGE":
        return FakeTensor(np.random.rand(1, 8, 8, 3).astype("float32"))
    if kind == "VIDEO":
        return FakeVideo()
    if kind == "AUDIO":
        return {"waveform": FakeTensor(np.zeros((1, 1, 16000), dtype="float32")), "sample_rate": 16000}
    if kind == "STRING":
        return cfg.get("default") or "test prompt"
    if kind in ("INT", "FLOAT"):
        return cfg["default"]
    if kind == "BOOLEAN":
        return cfg["default"]
    raise AssertionError(kind)


def typed_dict_keys(td_name):
    td = getattr(params, td_name, None)
    if td is None:
        return None, None
    return set(typing.get_type_hints(td)), set(td.__required_keys__)


class Recorder:
    def __init__(self, resource):
        self.resource = resource
        self.kwargs = None

    def generate(self, **kw):
        self.kwargs = kw
        out = os.path.join(kw["download_directory"], "x.bin")
        open(out, "wb").write(b"x")
        return types.SimpleNamespace(status="complete", error=None, downloaded_paths=[out], credits_charged=1,
                                     model_dump_json=lambda indent=0: "{}")


class T(unittest.TestCase):
    def run_spec(self, spec, drop=(), **override):
        node_cls = more.NODE_CLASS_MAPPINGS[spec.key]
        it = node_cls.INPUT_TYPES()
        values = {k: sample(d) for k, d in {**it["required"], **it.get("optional", {})}.items()}
        for k in drop:
            values.pop(k, None)
        values.update(override)
        rec = Recorder(spec.resource)
        client = types.SimpleNamespace(v1=types.SimpleNamespace(**{spec.resource: rec}))
        h.make_client = lambda: client
        h.to_comfy_video = lambda p: ("VIDEO", p)
        h.load_images = lambda paths: ("IMAGE", paths)
        h.load_audio = lambda p: ("AUDIO", p)
        node_cls().run(**values)
        return rec.kwargs

    def test_all_specs_match_real_sdk(self):
        self.assertEqual(len(ALL_SPECS), 25)
        for spec in ALL_SPECS:
            with self.subTest(spec.key):
                kw = self.run_spec(spec)
                real = getattr(REAL, spec.resource).generate
                sig = inspect.signature(real)
                sig.bind(**kw)  # raises TypeError on unknown/missing args
                # assets / style keys must exist in the SDK TypedDicts, required ones present
                resp = "".join(p.capitalize() for p in spec.resource.split("_"))
                for part, kind in (("assets", "Assets"), ("style", "Style")):
                    if part not in kw:
                        continue
                    found = False
                    for verb in ("Generate", "Create"):
                        keys, req = typed_dict_keys(f"V1{resp}{verb}Body{kind}")
                        if keys:
                            found = True
                            break
                    self.assertTrue(found, f"{spec.key}: no TypedDict for {part}")
                    self.assertFalse(set(kw[part]) - keys, f"{spec.key} {part} unknown keys {set(kw[part]) - keys}")
                    self.assertFalse(req - set(kw[part]), f"{spec.key} {part} missing {req - set(kw[part])}")

    def test_option_lists_nonempty_and_valid_for_sdk(self):
        for spec in ALL_SPECS:
            for name, decl in {**spec.required, **spec.optional}.items():
                if isinstance(decl[0], list):
                    self.assertTrue(decl[0], f"{spec.key}.{name} has no options")

    def test_image_editor_multi_image(self):
        spec = next(s for s in more.SPECS if s.resource == "ai_image_editor")
        self.assertEqual(len(self.run_spec(spec, drop=("image_3",))["assets"]["image_file_paths"]), 2)
        self.assertIn("image_file_path", self.run_spec(spec, drop=("image_2", "image_3"))["assets"])

    def test_animation_audio_source(self):
        spec = next(s for s in more.SPECS if s.resource == "animation")
        self.assertEqual(self.run_spec(spec, drop=("audio", "image"))["assets"]["audio_source"], "none")
        self.assertEqual(self.run_spec(spec, audio=sample(("AUDIO",)))["assets"]["audio_source"], "file")

    def test_upscaler_scale(self):
        spec = next(s for s in more.SPECS if s.resource == "ai_image_upscaler")
        self.assertEqual(self.run_spec(spec, scale_factor="4x")["scale_factor"], 4.0)

    def test_face_editor_sends_only_changed_sliders(self):
        spec = next(s for s in more.SPECS if s.resource == "ai_face_editor")
        style = self.run_spec(spec, mouth_smile=30.0)["style"]
        self.assertEqual(style["mouth_smile"], 30.0)
        self.assertNotIn("head_yaw", style)

    def test_voice_nodes_on_by_default_and_hideable(self):
        import subprocess
        code = (f"import sys; sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))!r});"
                f"import {PKG} as p; print('MagicHourVoiceCloner' in p.NODE_CLASS_MAPPINGS)")
        env = {k: v for k, v in os.environ.items() if k != "MAGIC_HOUR_DISABLE_VOICE_NODES"}
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(out.stdout.strip(), "True", out.stderr)
        env["MAGIC_HOUR_DISABLE_VOICE_NODES"] = "1"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertEqual(out.stdout.strip(), "False", out.stderr)


if __name__ == "__main__":
    unittest.main()
