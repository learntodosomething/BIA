import random
import numpy as np
from PIL import Image

def image_from_hash(hash_str, width, height, grayscale=False):
    seed = int(hash_str[:16], 16)
    random.seed(seed)

    if grayscale:
        data = np.zeros((height, width), dtype=np.uint8)
        for y in range(height):
            for x in range(width):
                data[y, x] = random.randint(0, 255)
        return Image.fromarray(data, "L")

    data = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            data[y, x] = [
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            ]

    return Image.fromarray(data, "RGB")
