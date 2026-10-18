# Magic Hour for ComfyUI

Custom nodes that run [Magic Hour](https://magichour.ai) generation tools inside a ComfyUI workflow, so you don't have to leave your graph or write API calls.

**Video** (return a `VIDEO`): Image to Video, Text to Video, Video to Video, Talking Photo, Lip Sync, Face Swap (Video), Character Replace, AI Video Editor, AI Video Translator, Audio to Video, Animation, Auto Subtitle Generator.

**Image** (return an `IMAGE`): AI Image Generator, AI Image Editor, AI Image Upscaler, AI Headshot Generator, AI Clothes Changer, AI Face Editor, Face Swap (Photo), Head Swap, Body Swap, Background Remover, Photo Colorizer, AI Meme Generator, AI QR Code Generator, AI GIF Generator (frames).

**Other:** Face Detection (returns the API's JSON as text).

**Voice** (return `AUDIO`, off by default): AI Voice Generator and AI Voice Cloner. Set `MAGIC_HOUR_ENABLE_VOICE_NODES=1` before starting ComfyUI to enable them. Only clone voices you have the right to use.

That is 29 tools in total, the same set as the Magic Hour Python SDK. Long option lists (art styles, voices, meme templates, languages) are read from the installed SDK, so they stay in sync with the API.

Each node uploads its inputs, starts the job, waits for it to finish, downloads the result into `ComfyUI/output/magic_hour/`, and returns it with the saved file path and the credits charged.

## Install

**Comfy Registry / ComfyUI-Manager:** search for "Magic Hour" (once published).

**Manual:**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/magichourhq/comfyui-magic-hour
pip install -r comfyui-magic-hour/requirements.txt
```

Restart ComfyUI. The nodes appear under **Magic Hour** in the node menu. Requires a ComfyUI version that has the `VIDEO` type (any recent release).

## API key

1. Create an API key at <https://magichour.ai/developer>.
2. Give it to ComfyUI **before it starts**, using either:
   - an environment variable: `export MAGIC_HOUR_API_KEY=...`, or
   - a file named `api_key.txt` inside this folder containing only the key (it is git-ignored).

The key is deliberately **not** a node field. Node field values are saved inside workflow files, so a key typed into a node would leak whenever the workflow is shared.

## Credits and usage

Every run spends credits on the account that owns the key. Longer videos, higher resolutions, and premium models cost more. See <https://magichour.ai/pricing> and the [API docs](https://docs.magichour.ai). Jobs run on Magic Hour's servers, so no GPU is needed locally.

Use the swap, clothes changer, face editor, lip sync, and voice nodes only with people's likenesses and voices you have the right to use, and follow Magic Hour's [terms](https://magichour.ai/terms) and content guidelines.

## Example workflow: photo to talking video

1. `Load Image` and `Load Audio` nodes.
2. Connect them to **Magic Hour: Talking Photo**.
3. Connect its `video` output to `Save Video` (or `Preview`).

## Troubleshooting

- **"API key not found"**: set `MAGIC_HOUR_API_KEY` before launching ComfyUI, or create `api_key.txt`.
- **401 Unauthorized**: the key is wrong or was deleted. Create a new one.
- **Not enough credits / plan limits**: the error message from Magic Hour is shown in the node. Some models and resolutions need a paid plan.
- **Slow**: video generation takes from tens of seconds to several minutes. The node waits until it's done.

## Development

```bash
python -m unittest discover tests   # mocked, spends no credits
```

## License

Apache-2.0, see `LICENSE`.
