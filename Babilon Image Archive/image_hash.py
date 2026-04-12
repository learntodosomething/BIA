import hashlib
from PIL import Image
import numpy as np

IMAGE_SIZE = (128, 128)

def image_to_hash(image: Image.Image) -> str:
    img = image.convert("RGB").resize(IMAGE_SIZE)
    data = img.tobytes()
    return hashlib.sha256(data).hexdigest()

def hash_to_seed(hash_str: str) -> int:
    return int(hash_str[:16], 16)
