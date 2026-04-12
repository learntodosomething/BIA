import warnings
import logging
import os

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.getLogger("diffusers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("accelerate").setLevel(logging.ERROR)

import torch

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)


def _best_device():
    """
    Visszaadja: (device_str, dtype, use_fp16_variant)
      CUDA  -> 'cuda',  float16, True   (NVIDIA GPU)
      MPS   -> 'mps',   float16, False  (Apple Silicon)
      CPU   -> 'cpu',   float32, False  (minden mas: Intel, AMD integralt, stb.)
    """
    if torch.cuda.is_available():
        return "cuda", torch.float16, True
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", torch.float16, False
    return "cpu", torch.float32, False


class AIServer:
    def __init__(self):
        device, dtype, use_variant = _best_device()
        self.device = device
        print(f"[AI] Eszkoz: {device.upper()}  dtype: {dtype}")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from diffusers import AutoPipelineForText2Image

            load_kwargs = {"torch_dtype": dtype}
            if use_variant:
                load_kwargs["variant"] = "fp16"

            print("[AI] Pipeline betoltese...")
            self.pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sdxl-turbo",
                **load_kwargs,
            )
            self.pipe.to(device)

            if device == "cuda":
                self.pipe.enable_attention_slicing()

            self.pipe.set_progress_bar_config(disable=True)

            # Warmup -- ha crashel, csak figyelmeztetunk, nem allunk le
            print("[AI] Warmup...")
            warmup_sz = 256 if device == "cpu" else 512
            try:
                with torch.inference_mode():
                    self.pipe(
                        prompt="warmup",
                        num_inference_steps=1,
                        guidance_scale=0.0,
                        width=warmup_sz,
                        height=warmup_sz,
                    )
                print(f"[AI] KESZ [{device.upper()}]")
            except Exception as warmup_err:
                # Warmup hiba nem fatalis
                print(f"[AI] Warmup figyelmezetes: {warmup_err}")
                print("[AI] KESZ (warmup nelkul)")

    def generate(self, prompt, width, height,
                 steps=2, cfg=0.0, negative_prompt="", **kwargs):
        width  = max(8, (width  // 8) * 8)
        height = max(8, (height // 8) * 8)

        if self.device == "cpu":
            width  = min(width,  512)
            height = min(height, 512)
            steps  = min(steps, 2)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with torch.inference_mode():
                img = self.pipe(
                    prompt=prompt,
                    num_inference_steps=steps,
                    guidance_scale=cfg,
                    width=width,
                    height=height,
                ).images[0]

        return img
