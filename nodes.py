"""Magic Hour nodes: Image-to-Video, Talking Photo, Face Swap, Character Replace.

Each node uploads its inputs, starts the job, waits for it, downloads the MP4,
and returns it as a ComfyUI VIDEO plus the saved file path. Generations spend
Magic Hour credits on the account that owns the API key.
"""

from . import helpers as h

CATEGORY = "Magic Hour"
VIDEO_OUTPUTS = ("VIDEO", "STRING", "INT")
VIDEO_OUTPUT_NAMES = ("video", "video_path", "credits_charged")

I2V_MODELS = [
    "default", "kling-3.0", "kling-2.6", "kling-2.5", "ltx-2.5", "ltx-2.3", "ltx-2",
    "seedance-2.5", "seedance-2.0", "seedance-2.0-mini", "seedance-1.5", "seedance",
    "veo3.1", "veo3.1-lite", "sora-2", "wan-3.0", "wan-2.2", "minimax-h3",
    "gemini-omni-1.1", "kling-1.6",
]


def _result(path, credits):
    return (h.to_comfy_video(path), path, int(credits or 0))


class MagicHourImageToVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "duration_seconds": ("FLOAT", {"default": 5.0, "min": 1.0, "max": 30.0, "step": 0.5}),
                "model": (I2V_MODELS, {"default": "default"}),
                "resolution": (["720p", "480p", "1080p", "4k"], {"default": "720p"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            }
        }

    RETURN_TYPES = VIDEO_OUTPUTS
    RETURN_NAMES = VIDEO_OUTPUT_NAMES
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "Animate an image into a video with Magic Hour. Costs Magic Hour credits."

    def run(self, image, duration_seconds, model, resolution, prompt):
        client = h.make_client()
        img = h.image_to_png(image)
        try:
            kwargs = dict(
                assets={"image_file_path": img},
                end_seconds=float(duration_seconds),
                resolution=resolution,
                name=f"comfyui-i2v-{h.stamp()}",
                wait_for_completion=True,
                download_outputs=True,
                download_directory=h.output_dir(),
            )
            if model != "default":
                kwargs["model"] = model
            if prompt.strip():
                kwargs["style"] = {"prompt": prompt.strip()}
            path, credits = h.finish(h.call(client.v1.image_to_video.generate, **kwargs))
        finally:
            h.cleanup(img)
        return _result(path, credits)


class MagicHourTalkingPhoto:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "audio": ("AUDIO",),
                "generation_mode": (["realistic", "prompted"], {"default": "realistic"}),
                "start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1}),
                "end_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1,
                                          "tooltip": "0 = use the whole audio (max 60s window)"}),
                "prompt": ("STRING", {"multiline": True, "default": "",
                                      "tooltip": "Only used in 'prompted' mode"}),
            }
        }

    RETURN_TYPES = VIDEO_OUTPUTS
    RETURN_NAMES = VIDEO_OUTPUT_NAMES
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "Make a photo talk using an audio clip (max 60s). Costs Magic Hour credits."

    def run(self, image, audio, generation_mode, start_seconds, end_seconds, prompt):
        client = h.make_client()
        img = h.image_to_png(image)
        wav, seconds = h.audio_to_wav(audio)
        try:
            start, end = h.resolve_window(start_seconds, end_seconds, min(seconds, h.MAX_AUDIO_SECONDS))
            style = {"generation_mode": generation_mode}
            if generation_mode == "prompted" and prompt.strip():
                style["prompt"] = prompt.strip()
            path, credits = h.finish(h.call(client.v1.ai_talking_photo.generate,
                assets={"image_file_path": img, "audio_file_path": wav},
                start_seconds=start,
                end_seconds=end,
                style=style,
                name=f"comfyui-talking-photo-{h.stamp()}",
                wait_for_completion=True,
                download_outputs=True,
                download_directory=h.output_dir(),
            ))
        finally:
            h.cleanup(img, wav)
        return _result(path, credits)


class MagicHourFaceSwap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "face_image": ("IMAGE",),
                "version": (["default", "v2", "v1"], {"default": "default"}),
                "start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1}),
                "end_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1,
                                          "tooltip": "0 = to the end of the video"}),
            }
        }

    RETURN_TYPES = VIDEO_OUTPUTS
    RETURN_NAMES = VIDEO_OUTPUT_NAMES
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "Swap all faces in a video with the face in an image. Only use faces you have "
        "the right to use. Costs Magic Hour credits."
    )

    def run(self, video, face_image, version, start_seconds, end_seconds):
        client = h.make_client()
        vid = h.video_to_mp4(video)
        img = h.image_to_png(face_image)
        try:
            start, end = h.resolve_window(start_seconds, end_seconds, h.video_duration(video))
            kwargs = dict(
                assets={
                    "face_swap_mode": "all-faces",
                    "video_source": "file",
                    "video_file_path": vid,
                    "image_file_path": img,
                },
                start_seconds=start,
                end_seconds=end,
                name=f"comfyui-face-swap-{h.stamp()}",
                wait_for_completion=True,
                download_outputs=True,
                download_directory=h.output_dir(),
            )
            if version != "default":
                kwargs["style"] = {"version": version}
            path, credits = h.finish(h.call(client.v1.face_swap.generate, **kwargs))
        finally:
            h.cleanup(vid, img)
        return _result(path, credits)


class MagicHourCharacterReplace:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "character_image": ("IMAGE",),
                "mode": (["replace", "animate"], {"default": "replace"}),
                "model": (["wan-animate", "kling-3.0"], {"default": "wan-animate"}),
                "resolution": (["720p", "480p", "1080p"], {"default": "720p"}),
                "start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1}),
                "end_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1,
                                          "tooltip": "0 = to the end of the video"}),
            }
        }

    RETURN_TYPES = VIDEO_OUTPUTS
    RETURN_NAMES = VIDEO_OUTPUT_NAMES
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = (
        "Replace the person in a video with your character image, or animate your "
        "character with the video's motion. wan-animate: 480p/720p. kling-3.0: 720p/1080p. "
        "Costs Magic Hour credits."
    )

    def run(self, video, character_image, mode, model, resolution, start_seconds, end_seconds):
        supported = {"wan-animate": {"480p", "720p"}, "kling-3.0": {"720p", "1080p"}}
        if resolution not in supported[model]:
            raise ValueError(f"{model} supports {sorted(supported[model])}, not {resolution}.")
        client = h.make_client()
        vid = h.video_to_mp4(video)
        img = h.image_to_png(character_image)
        try:
            start, end = h.resolve_window(start_seconds, end_seconds, h.video_duration(video))
            path, credits = h.finish(h.call(client.v1.character_replace.generate,
                assets={"video_file_path": vid, "image_file_path": img},
                start_seconds=start,
                end_seconds=end,
                model=model,
                resolution=resolution,
                style={"mode": mode},
                name=f"comfyui-character-replace-{h.stamp()}",
                wait_for_completion=True,
                download_outputs=True,
                download_directory=h.output_dir(),
            ))
        finally:
            h.cleanup(vid, img)
        return _result(path, credits)


NODE_CLASS_MAPPINGS = {
    "MagicHourImageToVideo": MagicHourImageToVideo,
    "MagicHourTalkingPhoto": MagicHourTalkingPhoto,
    "MagicHourFaceSwap": MagicHourFaceSwap,
    "MagicHourCharacterReplace": MagicHourCharacterReplace,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MagicHourImageToVideo": "Magic Hour: Image to Video",
    "MagicHourTalkingPhoto": "Magic Hour: Talking Photo",
    "MagicHourFaceSwap": "Magic Hour: Face Swap (Video)",
    "MagicHourCharacterReplace": "Magic Hour: Character Replace",
}
