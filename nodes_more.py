"""The remaining Magic Hour tools, declared as specs (see generic.py).

Together with the four hand-written nodes in nodes.py this covers every
generation tool in the Magic Hour Python SDK (plus face detection).
Voice nodes are off unless MAGIC_HOUR_ENABLE_VOICE_NODES=1.
"""

import os

from . import helpers as h
from .generic import (AUD, BOOL, COMBO, END, FLT, IMG, INT, START, STR, VID, Spec, make_node, window)
from .nodes import I2V_MODELS

TD = h.typed_dict_options
SIG = h.signature_options

RES_VIDEO = ["720p", "480p", "1080p"]
RES_IMAGE = ["auto", "640px", "1k", "2k", "4k"]
ASPECT_IMAGE = ["auto", "1:1", "16:9", "9:16", "4:3", "3:2", "2:3", "4:5"]
FREE_TIP = "Free plan tip: model flux-2-klein with resolution 640px."


def _opt(d, key, value, skip=("", None)):
    """Add key to dict d unless value is empty."""
    if value not in skip:
        d[key] = value


def _text(v, key):
    return (v.get(key) or "").strip()


# --- image outputs ----------------------------------------------------------

def _clothes(v, f, d):
    return {"assets": {"person_file_path": f["person"], "garment_file_path": f["garment"],
                       "garment_type": v["garment_type"]}}


FACE_SLIDERS = [
    "eye_gaze_horizontal", "eye_gaze_vertical", "eye_open_ratio", "eyebrow_direction",
    "head_pitch", "head_roll", "head_yaw", "lip_open_ratio", "mouth_grim",
    "mouth_position_horizontal", "mouth_position_vertical", "mouth_pout", "mouth_purse", "mouth_smile",
]


def _face_editor(v, f, d):
    style = {"enhance_face": bool(v["enhance_face"])}
    for k in FACE_SLIDERS:
        if v.get(k):
            style[k] = float(v[k])
    return {"assets": {"image_file_path": f["image"]}, "style": style}


def _gif(v, f, d):
    return {"style": {"prompt": v["prompt"]}, "output_format": "gif"}


def _headshot(v, f, d):
    kw = {"assets": {"image_file_path": f["image"]}}
    if _text(v, "prompt"):
        kw["style"] = {"prompt": _text(v, "prompt")}
    return kw


def _image_editor(v, f, d):
    paths = [f[k] for k in ("image", "image_2", "image_3") if k in f]
    assets = {"image_file_paths": paths} if len(paths) > 1 else {"image_file_path": paths[0]}
    kw = {"assets": assets, "style": {"prompt": v["prompt"]}, "image_count": float(v["image_count"]),
          "aspect_ratio": v["aspect_ratio"]}
    if v["model"] != "default":
        kw["model"] = v["model"]
    if v["resolution"] != "auto":
        kw["resolution"] = v["resolution"]
    return kw


def _image_generator(v, f, d):
    kw = {"style": {"prompt": v["prompt"]}, "image_count": int(v["image_count"]),
          "aspect_ratio": v["aspect_ratio"]}
    if v["model"] != "default":
        kw["model"] = v["model"]
    if v["resolution"] != "auto":
        kw["resolution"] = v["resolution"]
    return kw


def _upscaler(v, f, d):
    style = {"mode": v["mode"]}
    _opt(style, "prompt", _text(v, "prompt"))
    return {"assets": {"image_file_path": f["image"]}, "scale_factor": float(v["scale_factor"].rstrip("x")),
            "style": style}


def _meme(v, f, d):
    return {"style": {"template": v["template"], "topic": v["topic"], "search_web": bool(v["search_web"])}}


def _qr(v, f, d):
    return {"content": v["content"], "style": {"art_style": v["art_style"]}}


def _body_swap(v, f, d):
    return {"assets": {"person_file_path": f["person"], "scene_file_path": f["scene"]},
            "resolution": v["resolution"]}


def _face_swap_photo(v, f, d):
    return {"assets": {"target_file_path": f["target"], "source_file_path": f["source"],
                       "face_swap_mode": "all-faces"}}


def _head_swap(v, f, d):
    kw = {"assets": {"body_file_path": f["body"], "head_file_path": f["head"]}}
    if int(v["max_resolution"]) > 0:
        kw["max_resolution"] = int(v["max_resolution"])
    return kw


def _bg_remover(v, f, d):
    assets = {"image_file_path": f["image"]}
    if "background_image" in f:
        assets["background_image_file_path"] = f["background_image"]
    return {"assets": assets}


def _colorizer(v, f, d):
    return {"assets": {"image_file_path": f["image"]}}


def _face_detection(v, f, d):
    kw = {"assets": {"target_file_path": f["image"]}}
    if float(v["confidence_score"]) > 0:
        kw["confidence_score"] = float(v["confidence_score"])
    return kw


# --- video outputs ----------------------------------------------------------

def _video_editor(v, f, d):
    s, e = window(v, d, "video")
    kw = {"assets": {"video_file_path": f["video"]}, "style": {"prompt": v["prompt"]},
          "start_seconds": s, "end_seconds": e, "resolution": v["resolution"]}
    if v["model"] != "default":
        kw["model"] = v["model"]
    return kw


def _video_translator(v, f, d):
    s, e = window(v, d, "video")
    return {"assets": {"video_file_path": f["video"]}, "target_language": v["target_language"],
            "start_seconds": s, "end_seconds": e, "resolution": v["resolution"]}


def _animation(v, f, d):
    assets = {"audio_source": "file" if "audio" in f else "none"}
    if "audio" in f:
        assets["audio_file_path"] = f["audio"]
    if "image" in f:
        assets["image_file_path"] = f["image"]
    style = {"art_style": v["art_style"], "camera_effect": v["camera_effect"],
             "prompt_type": v["prompt_type"], "transition_speed": int(v["transition_speed"])}
    _opt(style, "prompt", _text(v, "prompt"))
    _opt(style, "art_style_custom", _text(v, "art_style_custom"))
    return {"assets": assets, "style": style, "end_seconds": float(v["duration_seconds"]),
            "fps": float(v["fps"]), "width": int(v["width"]), "height": int(v["height"])}


def _audio_to_video(v, f, d):
    s, e = window(v, d, "audio")
    assets = {"audio_file_path": f["audio"]}
    if "image" in f:
        assets["image_file_path"] = f["image"]
    kw = {"assets": assets, "start_seconds": s, "end_seconds": e, "resolution": v["resolution"]}
    if _text(v, "prompt"):
        kw["style"] = {"prompt": _text(v, "prompt")}
    return kw


def _subtitles(v, f, d):
    s, e = window(v, d, "video")
    return {"assets": {"video_file_path": f["video"]}, "style": {"template": v["template"]},
            "start_seconds": s, "end_seconds": e}


def _lip_sync(v, f, d):
    s, e = window(v, d, "video", "audio")
    return {"assets": {"video_source": "file", "video_file_path": f["video"], "audio_file_path": f["audio"]},
            "style": {"generation_mode": v["generation_mode"]}, "start_seconds": s, "end_seconds": e}


def _text_to_video(v, f, d):
    kw = {"style": {"prompt": v["prompt"]}, "end_seconds": float(v["duration_seconds"]),
          "aspect_ratio": v["aspect_ratio"], "resolution": v["resolution"], "audio": bool(v["audio"])}
    if v["model"] != "default":
        kw["model"] = v["model"]
    return kw


def _video_to_video(v, f, d):
    s, e = window(v, d, "video")
    style = {"art_style": v["art_style"], "prompt_type": v["prompt_type"], "version": v["version"]}
    if v["model"] != "default":
        style["model"] = v["model"]
    _opt(style, "prompt", _text(v, "prompt"))
    return {"assets": {"video_source": "file", "video_file_path": f["video"]}, "style": style,
            "start_seconds": s, "end_seconds": e, "fps_resolution": v["fps_resolution"]}


# --- audio outputs (voice nodes, opt-in) -------------------------------------

def _voice_cloner(v, f, d):
    return {"assets": {"audio_file_path": f["audio"]}, "style": {"prompt": v["prompt"]}}


def _voice_generator(v, f, d):
    return {"style": {"prompt": v["prompt"], "voice_name": v["voice_name"]}}


# --- the table ---------------------------------------------------------------

_face_sliders = {k: FLT(0, -100, 100, 5) for k in FACE_SLIDERS}
_img_models = SIG("ai_image_editor", "model", ["default"])
_gen_models = SIG("ai_image_generator", "model", ["default"])

SPECS = [
    Spec("MagicHourClothesChanger", "Magic Hour: AI Clothes Changer", "ai_clothes_changer", "image",
         "Put a garment onto a person in a photo. Use only photos you have the right to use.",
         {"person": IMG(), "garment": IMG(),
          "garment_type": COMBO(["entire_outfit", "upper_body", "lower_body", "dresses"])}, _clothes),
    Spec("MagicHourFaceEditor", "Magic Hour: AI Face Editor", "ai_face_editor", "image",
         "Adjust expression and head pose of a face (sliders -100 to 100; 0 = unchanged).",
         {"image": IMG(), "enhance_face": BOOL(False), **_face_sliders}, _face_editor),
    Spec("MagicHourGifGenerator", "Magic Hour: AI GIF Generator", "ai_gif_generator", "image",
         "Generate an animated GIF from a prompt (returned as a batch of frames).",
         {"prompt": STR("", True)}, _gif),
    Spec("MagicHourHeadshot", "Magic Hour: AI Headshot Generator", "ai_headshot_generator", "image",
         "Turn a photo into a professional headshot.",
         {"image": IMG()}, _headshot, {"prompt": STR("", True)}),
    Spec("MagicHourImageEditor", "Magic Hour: AI Image Editor", "ai_image_editor", "image",
         "Edit one or more images with a text prompt. " + FREE_TIP,
         {"image": IMG(), "prompt": STR("", True), "model": COMBO(_img_models, "default"),
          "aspect_ratio": COMBO(ASPECT_IMAGE, "auto"), "resolution": COMBO(RES_IMAGE, "auto"),
          "image_count": INT(1, 1, 4)}, _image_editor, {"image_2": IMG(), "image_3": IMG()}),
    Spec("MagicHourImageGenerator", "Magic Hour: AI Image Generator", "ai_image_generator", "image",
         "Generate images from a text prompt. " + FREE_TIP,
         {"prompt": STR("", True), "model": COMBO(_gen_models, "default"),
          "aspect_ratio": COMBO(["1:1", "16:9", "9:16"], "1:1"), "resolution": COMBO(RES_IMAGE, "auto"),
          "image_count": INT(1, 1, 4)}, _image_generator),
    Spec("MagicHourUpscaler", "Magic Hour: AI Image Upscaler", "ai_image_upscaler", "image",
         "Upscale an image 2x or 4x.",
         {"image": IMG(), "scale_factor": COMBO(["2x", "4x"], "2x"),
          "mode": COMBO(["balanced", "creative", "preserve", "pro"], "balanced")},
         _upscaler, {"prompt": STR("", True)}),
    Spec("MagicHourMemeGenerator", "Magic Hour: AI Meme Generator", "ai_meme_generator", "image",
         "Make a meme from a template and a topic.",
         {"topic": STR("", True),
          "template": COMBO(TD("V1AiMemeGeneratorCreateBodyStyle", "template", ["Drake Hotline Bling"])),
          "search_web": BOOL(False)}, _meme),
    Spec("MagicHourQrCode", "Magic Hour: AI QR Code Generator", "ai_qr_code_generator", "image",
         "Create an artistic QR code for a URL or text.",
         {"content": STR("https://", False), "art_style": STR("", True)}, _qr),
    Spec("MagicHourBodySwap", "Magic Hour: Body Swap", "body_swap", "image",
         "Place a person from one photo into another scene. Use only photos you have the right to use.",
         {"person": IMG(), "scene": IMG(), "resolution": COMBO(["640px", "1k", "2k", "4k"], "640px")}, _body_swap),
    Spec("MagicHourFaceSwapPhoto", "Magic Hour: Face Swap (Photo)", "face_swap_photo", "image",
         "Swap the faces in a target photo with the face from a source photo. Use only faces you have the right to use.",
         {"target": IMG(), "source": IMG()}, _face_swap_photo),
    Spec("MagicHourHeadSwap", "Magic Hour: Head Swap", "head_swap", "image",
         "Put one person's head on another's body. Use only photos you have the right to use.",
         {"body": IMG(), "head": IMG(), "max_resolution": INT(0, 0, 2048, 64, "0 = your plan's maximum")}, _head_swap),
    Spec("MagicHourBackgroundRemover", "Magic Hour: Background Remover", "image_background_remover", "image",
         "Remove (or replace) an image's background.",
         {"image": IMG()}, _bg_remover, {"background_image": IMG()}),
    Spec("MagicHourPhotoColorizer", "Magic Hour: Photo Colorizer", "photo_colorizer", "image",
         "Colorize a black-and-white photo.", {"image": IMG()}, _colorizer),
    Spec("MagicHourVideoEditor", "Magic Hour: AI Video Editor", "ai_video_editor", "video",
         "Edit a video with a text prompt.",
         {"video": VID(), "prompt": STR("", True),
          "model": COMBO(["default"] + SIG("ai_video_editor", "model", []), "default"),
          "resolution": COMBO(RES_VIDEO, "720p"), "start_seconds": START(), "end_seconds": END()}, _video_editor),
    Spec("MagicHourVideoTranslator", "Magic Hour: AI Video Translator", "ai_video_translator", "video",
         "Translate a video's speech into another language.",
         {"video": VID(), "target_language": COMBO(SIG("ai_video_translator", "target_language", ["English"]), "English"),
          "resolution": COMBO(RES_VIDEO, "720p"), "start_seconds": START(), "end_seconds": END()}, _video_translator),
    Spec("MagicHourAnimation", "Magic Hour: Animation", "animation", "video",
         "Create a stylized animation, optionally from an image and an audio track. Width/height are capped by your plan.",
         {"art_style": COMBO(TD("V1AnimationCreateBodyStyle", "art_style", ["3D Render"])),
          "camera_effect": COMBO(TD("V1AnimationCreateBodyStyle", "camera_effect", ["Accelerate"])),
          "prompt_type": COMBO(["ai_choose", "custom", "use_lyrics"], "ai_choose"),
          "prompt": STR("", True), "art_style_custom": STR("", False),
          "transition_speed": INT(5, 1, 10), "duration_seconds": FLT(10.0, 1.0, 300.0, 0.5),
          "fps": FLT(12.0, 1.0, 60.0, 1.0), "width": INT(960, 64, 4096, 8), "height": INT(540, 64, 4096, 8)},
         _animation, {"image": IMG(), "audio": AUD()}),
    Spec("MagicHourAudioToVideo", "Magic Hour: Audio to Video", "audio_to_video", "video",
         "Make a video from an audio track (optionally with an image).",
         {"audio": AUD(), "resolution": COMBO(RES_VIDEO, "720p"), "start_seconds": START(), "end_seconds": END(),
          "prompt": STR("", True)}, _audio_to_video, {"image": IMG()}),
    Spec("MagicHourAutoSubtitles", "Magic Hour: Auto Subtitle Generator", "auto_subtitle_generator", "video",
         "Add subtitles to a video.",
         {"video": VID(), "template": COMBO(["cinematic", "highlight", "karaoke", "minimalist"], "highlight"),
          "start_seconds": START(), "end_seconds": END()}, _subtitles),
    Spec("MagicHourLipSync", "Magic Hour: Lip Sync", "lip_sync", "video",
         "Sync a video's mouth movement to an audio track (max 60s window). Use only footage you have the right to use.",
         {"video": VID(), "audio": AUD(), "generation_mode": COMBO(["standard", "lite", "pro"], "standard"),
          "start_seconds": START(), "end_seconds": END()}, _lip_sync),
    Spec("MagicHourTextToVideo", "Magic Hour: Text to Video", "text_to_video", "video",
         "Generate a video from a text prompt.",
         {"prompt": STR("", True), "duration_seconds": FLT(5.0, 1.0, 30.0, 0.5), "model": COMBO(I2V_MODELS, "default"),
          "resolution": COMBO(["720p", "480p", "1080p", "4k"], "720p"),
          "aspect_ratio": COMBO(["16:9", "9:16", "1:1"], "16:9"), "audio": BOOL(False)}, _text_to_video),
    Spec("MagicHourVideoToVideo", "Magic Hour: Video to Video", "video_to_video", "video",
         "Restyle a video with an art style.",
         {"video": VID(), "art_style": COMBO(TD("V1VideoToVideoCreateBodyStyle", "art_style", ["3D Render"])),
          "model": COMBO(TD("V1VideoToVideoCreateBodyStyle", "model", ["default"]), "default"),
          "prompt_type": COMBO(["default", "append_default", "custom"], "default"), "prompt": STR("", True),
          "version": COMBO(["default", "v1", "v2"], "default"), "fps_resolution": COMBO(["HALF", "FULL"], "HALF"),
          "start_seconds": START(), "end_seconds": END()}, _video_to_video),
    Spec("MagicHourFaceDetection", "Magic Hour: Face Detection", "face_detection", "data",
         "Detect faces in an image. Returns the API's JSON result as text.",
         {"image": IMG(), "confidence_score": FLT(0.0, 0.0, 1.0, 0.05, "0 = API default")}, _face_detection,
         send_name=False),
]

VOICE_SPECS = [
    Spec("MagicHourVoiceGenerator", "Magic Hour: AI Voice Generator", "ai_voice_generator", "audio",
         "Generate speech from text in a chosen voice.",
         {"prompt": STR("", True),
          "voice_name": COMBO(TD("V1AiVoiceGeneratorCreateBodyStyle", "voice_name", ["Aang (Avatar)"]))},
         _voice_generator),
    Spec("MagicHourVoiceCloner", "Magic Hour: AI Voice Cloner", "ai_voice_cloner", "audio",
         "Speak text in the voice of a reference audio clip. Only use voices you have the right to use.",
         {"audio": AUD(), "prompt": STR("", True)}, _voice_cloner),
]

if os.environ.get("MAGIC_HOUR_ENABLE_VOICE_NODES") == "1":
    SPECS = SPECS + VOICE_SPECS

NODE_CLASS_MAPPINGS = {s.key: make_node(s) for s in SPECS}
NODE_DISPLAY_NAME_MAPPINGS = {s.key: s.display for s in SPECS}
