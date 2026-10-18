"""Turns a small declarative spec into a ComfyUI node.

A spec says which inputs a tool takes, how to turn them into the SDK's
`generate()` arguments, and what kind of output comes back. The shared runner
handles the repetitive parts: API key, uploading inputs as temp files, waiting
for the job, downloading, converting the result to a ComfyUI type, and cleanup.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict

from . import helpers as h

CATEGORY = "Magic Hour"
MEDIA_TYPES = ("IMAGE", "VIDEO", "AUDIO")

OUTPUTS = {
    "video": (("VIDEO", "STRING", "INT"), ("video", "video_path", "credits_charged")),
    "image": (("IMAGE", "STRING", "INT"), ("image", "image_paths", "credits_charged")),
    "audio": (("AUDIO", "STRING", "INT"), ("audio", "audio_path", "credits_charged")),
    "data": (("STRING",), ("json",)),
}


@dataclass
class Spec:
    key: str  # ComfyUI node id, e.g. "MagicHourLipSync"
    display: str
    resource: str  # attribute of client.v1, e.g. "lip_sync"
    kind: str  # video | image | audio | data
    description: str
    required: Dict[str, tuple]
    build: Callable  # build(v, files, durations) -> generate() kwargs
    optional: Dict[str, tuple] = field(default_factory=dict)
    send_name: bool = True  # face_detection.generate() has no `name` parameter


# --- input declaration helpers (return ComfyUI input tuples) ---------------

def IMG():
    return ("IMAGE",)


def VID():
    return ("VIDEO",)


def AUD():
    return ("AUDIO",)


def STR(default="", multiline=False, tooltip=None):
    cfg = {"default": default, "multiline": multiline}
    if tooltip:
        cfg["tooltip"] = tooltip
    return ("STRING", cfg)


def INT(default, lo, hi, step=1, tooltip=None):
    cfg = {"default": default, "min": lo, "max": hi, "step": step}
    if tooltip:
        cfg["tooltip"] = tooltip
    return ("INT", cfg)


def FLT(default, lo, hi, step=0.1, tooltip=None):
    cfg = {"default": default, "min": lo, "max": hi, "step": step}
    if tooltip:
        cfg["tooltip"] = tooltip
    return ("FLOAT", cfg)


def BOOL(default=False):
    return ("BOOLEAN", {"default": default})


def COMBO(options, default=None):
    options = list(options)
    cfg = {"default": default if default in options else options[0]}
    return (options, cfg)


def START():
    return FLT(0.0, 0.0, 3600.0, 0.1)


def END():
    return FLT(0.0, 0.0, 3600.0, 0.1, tooltip="0 = to the end of the clip")


def window(v, durations, *sources):
    """(start, end) from the start_seconds/end_seconds widgets and input clip lengths."""
    lengths = [durations[s] for s in sources if durations.get(s)]
    available = min(lengths) if lengths else None
    return h.resolve_window(v.get("start_seconds", 0.0), v.get("end_seconds", 0.0), available)


def duration_window(v):
    """For tools where end_seconds is the output length (no input clip)."""
    return float(v["duration_seconds"])


def _prepare_inputs(spec, v):
    files, durations, temps = {}, {}, []
    types = {**spec.required, **spec.optional}
    for name, decl in types.items():
        kind = decl[0]
        value = v.get(name)
        if kind not in MEDIA_TYPES or value is None:
            continue
        if kind == "IMAGE":
            path = h.image_to_png(value)
        elif kind == "VIDEO":
            path = h.video_to_mp4(value)
            durations[name] = h.video_duration(value)
        else:
            path, seconds = h.audio_to_wav(value)
            durations[name] = min(seconds, h.MAX_AUDIO_SECONDS)
        files[name] = path
        temps.append(path)
    return files, durations, temps


def execute(spec, v):
    client = h.make_client()
    files, durations, temps = _prepare_inputs(spec, v)
    try:
        kwargs = spec.build(v, files, durations)
        if spec.send_name:
            kwargs.setdefault("name", f"comfyui-{spec.resource.replace('_', '-')}-{h.stamp()}")
        kwargs.update(
            wait_for_completion=True,
            download_outputs=True,
            download_directory=h.output_dir(),
        )
        response = h.call(getattr(client.v1, spec.resource).generate, **kwargs)
        if spec.kind == "data":
            return (response.model_dump_json(indent=2),)
        paths, credits = h.finish_all(response)
        credits = int(credits or 0)
        if spec.kind == "video":
            return (h.to_comfy_video(paths[0]), paths[0], credits)
        if spec.kind == "image":
            return (h.load_images(paths), "\n".join(paths), credits)
        return (h.load_audio(paths[0]), paths[0], credits)
    finally:
        h.cleanup(*temps)


def make_node(spec):
    types, names = OUTPUTS[spec.kind]

    def input_types(cls):
        out = {"required": dict(spec.required)}
        if spec.optional:
            out["optional"] = dict(spec.optional)
        return out

    def run(self, **v):
        return execute(spec, v)

    return type(
        spec.key,
        (),
        {
            "INPUT_TYPES": classmethod(input_types),
            "RETURN_TYPES": types,
            "RETURN_NAMES": names,
            "FUNCTION": "run",
            "CATEGORY": CATEGORY,
            "DESCRIPTION": spec.description + " Costs Magic Hour credits.",
            "run": run,
            "SPEC": spec,
        },
    )
