import numpy as np
from PIL import Image
import random

IMAGE_SIZE = (128, 128)

def generate_image_from_hash(hash_str: str) -> Image.Image:
    seed = int(hash_str[:16], 16)
    random.seed(seed)

    data = np.zeros((IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)

    for y in range(IMAGE_SIZE[1]):
        for x in range(IMAGE_SIZE[0]):
            data[y, x] = [
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            ]

    return Image.fromarray(data)
