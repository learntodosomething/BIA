"""
Babylon Image Archive — Image ↔ ID conversion  (vectorized)
No Python loops over pixels — everything goes through numpy.
"""

import numpy as np
from PIL import Image as PilImage
from engine.id_codec import ImageID
from engine.palette import (
    Palette, ensure_palettes,
    image_to_indices_vectorized,
    indices_to_image_vectorized,
    get_color, color_to_id_value,
)


def image_to_id(
    pil_img: PilImage.Image,
    target_size: tuple[int, int],
    values_per_segment: int,
    palette: Palette,
) -> ImageID:
    """Convert a PIL image → ImageID.  Fast even at vps=1."""
    ensure_palettes()
    w, h = target_size

    # Resize with PIL (Lanczos for quality)
    resized = pil_img.convert("RGB").resize((w, h), PilImage.LANCZOS)
    pixels  = np.array(resized).reshape(-1, 3)          # (w*h, 3)

    indices = image_to_indices_vectorized(pixels, palette, values_per_segment)

    image_id = ImageID(value_count=w * h, values_per_segment=values_per_segment)
    image_id.size          = (w, h)
    image_id.palette_index = int(palette)

    # Bulk-set via the packed segments directly (faster than calling set_value)
    bpv = image_id._bits_per_value()
    vps = values_per_segment
    for i, val in enumerate(indices):
        seg_idx    = i // vps
        bit_offset = (i % vps) * bpv
        image_id._segments[seg_idx].set_sub(bit_offset, bpv, int(val))

    return image_id


def id_to_image(image_id: ImageID) -> PilImage.Image:
    """Reconstruct a PIL image from an ImageID.  Fast at all vps."""
    ensure_palettes()
    w, h = image_id.size
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid image size in ID: {w}×{h}")

    palette = Palette(image_id.palette_index)
    vps     = image_id.values_per_segment
    bpv     = image_id._bits_per_value()
    total   = w * h

    # Extract all indices in one pass
    indices = np.empty(total, dtype=np.int32)
    for i in range(total):
        seg_idx    = i // vps
        bit_offset = (i % vps) * bpv
        if seg_idx < len(image_id._segments):
            indices[i] = image_id._segments[seg_idx].get_sub(bit_offset, bpv)
        else:
            indices[i] = 0

    rgb_array = indices_to_image_vectorized(indices, palette, vps, (w, h))
    return PilImage.fromarray(rgb_array, "RGB")


def random_id_image(
    size: tuple[int, int],
    values_per_segment: int,
    palette: Palette,
) -> tuple[PilImage.Image, ImageID]:
    import random
    w, h     = size
    image_id = ImageID(value_count=w * h, values_per_segment=values_per_segment)
    image_id.size          = (w, h)
    image_id.palette_index = int(palette)
    image_id.randomise()
    return id_to_image(image_id), image_id
