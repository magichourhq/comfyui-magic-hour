"""Pure helpers: API key lookup, temp-file conversion, result handling.

Heavy imports (torch, PIL) happen inside functions so this module can be
imported and unit-tested without ComfyUI installed.
"""

import os
import tempfile
import time
import wave

KEY_ENV = "MAGIC_HOUR_API_KEY"
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.txt")
MAX_AUDIO_SECONDS = 60.0


def get_api_key():
    """API key from the MAGIC_HOUR_API_KEY env var, else api_key.txt next to this file.

    The key is deliberately not a node widget: widget values are saved inside
    workflow JSON and leak when a workflow is shared.
    """
    key = os.environ.get(KEY_ENV, "").strip()
    if not key and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        raise RuntimeError(
            "Magic Hour API key not found. Set the MAGIC_HOUR_API_KEY environment "
            "variable before starting ComfyUI, or put the key in "
            f"{KEY_FILE}. Create a key at https://magichour.ai/developer"
        )
    return key


def make_client():
    from magic_hour import Client

    # The SDK polls every 0.5s by default; 3s is plenty for minutes-long jobs.
    os.environ.setdefault("MAGIC_HOUR_POLL_INTERVAL", "3")
    return Client(token=get_api_key(), timeout=120)


def temp_path(suffix):
    fd, path = tempfile.mkstemp(prefix="magichour_", suffix=suffix)
    os.close(fd)
    return path


def image_to_png(image_tensor):
    """First image of a ComfyUI IMAGE batch ([B,H,W,C] floats 0-1) -> temp PNG path."""
    import numpy as np
    from PIL import Image

    arr = image_tensor[0].detach().cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    path = temp_path(".png")
    Image.fromarray(arr).save(path, format="PNG")
    return path


def video_to_mp4(video):
    """ComfyUI VIDEO input -> temp MP4 path."""
    path = temp_path(".mp4")
    video.save_to(path)
    return path


def video_duration(video):
    try:
        return float(video.get_duration())
    except Exception:
        return None


def audio_to_wav(audio):
    """ComfyUI AUDIO dict ({'waveform': [B,C,T], 'sample_rate': int}) -> (wav path, seconds)."""
    import numpy as np

    waveform = audio["waveform"][0].detach().cpu().numpy()  # [C, T]
    sample_rate = int(audio["sample_rate"])
    channels, frames = waveform.shape
    pcm = (np.clip(waveform.T, -1.0, 1.0) * 32767.0).astype("<i2")  # [T, C]
    path = temp_path(".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return path, frames / float(sample_rate)


def resolve_window(start, end, available):
    """Turn node inputs into (start, end) seconds. end == 0 means 'to the end of the clip'."""
    start = float(start)
    if end and float(end) > 0:
        end = float(end)
    elif available:
        end = float(available)
    else:
        raise ValueError("end_seconds is 0 and the clip length is unknown; set end_seconds.")
    if end <= start:
        raise ValueError(f"end_seconds ({end}) must be greater than start_seconds ({start}).")
    return start, end


def output_dir():
    try:
        import folder_paths

        base = folder_paths.get_output_directory()
    except Exception:
        base = os.path.join(os.getcwd(), "output")
    path = os.path.join(base, "magic_hour")
    os.makedirs(path, exist_ok=True)
    return path


def finish(response):
    """Validate an SDK response and return the downloaded file path."""
    status = getattr(response, "status", None)
    if status != "complete":
        err = getattr(response, "error", None)
        detail = getattr(err, "message", None) or err or "no error details"
        raise RuntimeError(f"Magic Hour job ended with status '{status}': {detail}")
    paths = getattr(response, "downloaded_paths", None) or []
    if not paths:
        raise RuntimeError("Magic Hour job completed but no output file was downloaded.")
    return paths[0], getattr(response, "credits_charged", None)


def to_comfy_video(path):
    """Wrap an MP4 path as a ComfyUI VIDEO value across ComfyUI versions."""
    try:
        from comfy_api.latest import InputImpl

        return InputImpl.VideoFromFile(path)
    except Exception:
        pass
    try:
        from comfy_api.input_impl import VideoFromFile

        return VideoFromFile(path)
    except Exception as exc:
        raise RuntimeError(
            "This ComfyUI version has no VIDEO type. Update ComfyUI, or use the "
            f"'video_path' STRING output (file saved at {path})."
        ) from exc


def cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def api_error_message(exc):
    """Readable text for a Magic Hour ApiError, or None if exc is not one."""
    resp = getattr(exc, "response", None)
    if resp is None or not hasattr(resp, "status_code"):
        return None
    detail = None
    try:
        body = resp.json()
        detail = body.get("message") or body.get("error") or str(body)
    except Exception:
        detail = getattr(resp, "text", None)
    status = resp.status_code
    hint = ""
    if status == 401:
        hint = " Check that your API key is correct and was not deleted."
    elif status == 402:
        hint = " This setting or model needs a paid plan or more credits; try a lower resolution or check your balance at https://magichour.ai."
    elif status == 422:
        hint = " The chosen model, resolution, or duration combination is not supported; try the default model or another resolution."
    return f"Magic Hour API error {status}: {detail}.{hint}"


def call(fn, **kwargs):
    """Run an SDK generate call, turning API errors into short readable ones."""
    try:
        return fn(**kwargs)
    except Exception as exc:
        msg = api_error_message(exc)
        if msg is None:
            raise
        raise RuntimeError(msg) from None


# ---------------------------------------------------------------------------
# Helpers for the spec-driven nodes (generic.py / nodes_more.py)
# ---------------------------------------------------------------------------

def _literal_values(tp):
    """Collect string values from a (possibly nested Optional/Union) Literal type."""
    import typing

    out = []
    for arg in typing.get_args(tp):
        if isinstance(arg, str):
            out.append(arg)
        elif typing.get_args(arg):
            out.extend(_literal_values(arg))
    return out


def typed_dict_options(td_name, field, fallback):
    """Allowed values of a Literal field in the SDK's params, read at import time.

    Reading them from the installed SDK keeps long lists (art styles, voices, meme
    templates) in sync with the API instead of being copied into this repo.
    """
    try:
        import typing

        from magic_hour.types import params

        hints = typing.get_type_hints(getattr(params, td_name))
        vals = _literal_values(hints[field])
        return vals or list(fallback)
    except Exception:
        return list(fallback)


def signature_options(resource, param, fallback):
    """Allowed values of a Literal parameter of <resource>.generate()."""
    try:
        import importlib
        import inspect

        mod = importlib.import_module(f"magic_hour.resources.v1.{resource}.client")
        cls = next(
            c
            for n, c in vars(mod).items()
            if inspect.isclass(c) and n.endswith("Client") and not n.startswith("Async") and hasattr(c, "generate")
        )
        ann = inspect.signature(cls.generate).parameters[param].annotation
        vals = _literal_values(ann)
        return vals or list(fallback)
    except Exception:
        return list(fallback)


def finish_all(response):
    """Like finish(), but returns every downloaded file path."""
    status = getattr(response, "status", None)
    if status != "complete":
        err = getattr(response, "error", None)
        detail = getattr(err, "message", None) or err or "no error details"
        raise RuntimeError(f"Magic Hour job ended with status '{status}': {detail}")
    paths = list(getattr(response, "downloaded_paths", None) or [])
    if not paths:
        raise RuntimeError("Magic Hour job completed but no output file was downloaded.")
    return paths, getattr(response, "credits_charged", None)


def load_images(paths, max_frames=64):
    """Downloaded image files -> ComfyUI IMAGE batch ([B,H,W,3] float32 0-1).

    Animated files (GIF) contribute their frames. Images whose size differs from
    the first are resized to match it so they can share one batch.
    """
    import numpy as np
    import torch
    from PIL import Image, ImageSequence

    frames = []
    for p in paths:
        with Image.open(p) as im:
            for i, fr in enumerate(ImageSequence.Iterator(im)):
                if i >= max_frames:
                    break
                frames.append(fr.convert("RGB"))
    if not frames:
        raise RuntimeError("No readable image in the Magic Hour output.")
    size = frames[0].size
    arrays = []
    for fr in frames:
        if fr.size != size:
            fr = fr.resize(size)
        arrays.append(np.asarray(fr, dtype=np.float32) / 255.0)
    return torch.from_numpy(np.stack(arrays))


def load_audio(path):
    """Downloaded audio file -> ComfyUI AUDIO dict, decoded with PyAV (bundled with ComfyUI)."""
    import av
    import numpy as np
    import torch

    chunks = []
    with av.open(path) as container:
        stream = container.streams.audio[0]
        rate = stream.rate
        resampler = av.AudioResampler(format="fltp", layout=stream.layout.name, rate=rate)
        for frame in container.decode(stream):
            out = resampler.resample(frame)
            for f in out if isinstance(out, list) else [out]:
                if f is not None:
                    chunks.append(f.to_ndarray())
    if not chunks:
        raise RuntimeError("No audio decoded from the Magic Hour output.")
    wave_arr = np.concatenate(chunks, axis=1).astype(np.float32)  # [C, T]
    return {"waveform": torch.from_numpy(wave_arr).unsqueeze(0), "sample_rate": int(rate)}
