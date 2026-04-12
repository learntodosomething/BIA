import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

class AIGenerator:
    def __init__(self, model_path):
        device = "cuda" if torch.cuda.is_available() else "cpu"

        self.pipe = StableDiffusionPipeline.from_single_file(
            model_path,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            safety_checker=None
        )

        self.pipe = self.pipe.to(device)

        if device == "cuda":
            self.pipe.enable_attention_slicing()

    def generate(
        self,
        prompt,
        width,
        height,
        steps=25,
        guidance=7.5,
        seed=None
    ) -> Image.Image:

        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.pipe.device).manual_seed(seed)

        image = self.pipe(
            prompt=prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=generator
        ).images[0]

        return image
