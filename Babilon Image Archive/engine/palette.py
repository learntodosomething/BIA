import math
import numpy as np
from enum import IntEnum

INT_BITS = 15
MAX_CV   = 1 << INT_BITS   # 32768

# KDTree küszöb: ennél nagyobb palettánál KDTree-t használunk
KDTREE_THRESHOLD = 512


class Palette(IntEnum):
    GRAYSCALE = 0
    COLOR     = 1


# LUT: _lut[palette][exp_index] = np.ndarray shape (count, 3) uint8
_lut: list = []
_kdtrees: list = []   # _kdtrees[palette][exp_index] = cKDTree or None
_ready = False


def _hsv_to_rgb(h: float, s: float, v: float):
    h = h % 360.0; s /= 100.0; v /= 100.0
    C = s * v
    X = C * (1.0 - abs(math.fmod(h / 60.0, 2.0) - 1.0))
    m = v - C
    if   h < 60:   r, g, b = C, X, 0.0
    elif h < 120:  r, g, b = X, C, 0.0
    elif h < 180:  r, g, b = 0.0, C, X
    elif h < 240:  r, g, b = 0.0, X, C
    elif h < 300:  r, g, b = X, 0.0, C
    else:           r, g, b = C, 0.0, X
    return int((r+m)*255), int((g+m)*255), int((b+m)*255)


def init_palettes():
    global _lut, _kdtrees, _ready
    from scipy.spatial import cKDTree

    _lut     = []
    _kdtrees = []

    for pal in range(len(Palette)):
        exp_table  = []
        tree_table = []
        for exp_i in range(INT_BITS):
            count  = 1 << (exp_i + 1)
            colors = np.zeros((count, 3), dtype=np.uint8)
            for ci in range(count):
                if pal == int(Palette.GRAYSCALE):
                    v = int(ci * 255.0 / count)
                    colors[ci] = (v, v, v)
                else:
                    num_shades = 4  if exp_i < INT_BITS - 1 else 50
                    num_tints  = 3  if exp_i < INT_BITS - 1 else 20
                    hue = (ci * 360.0 / count) % 360.0
                    mod = ci % (1 + num_shades + num_tints)
                    if mod == 0:
                        colors[ci] = _hsv_to_rgb(hue, 100, 100)
                    elif mod < 1 + num_shades:
                        colors[ci] = _hsv_to_rgb(hue, 100, mod*(100/(num_shades+1)))
                    else:
                        colors[ci] = _hsv_to_rgb(hue, (mod-num_shades)*(100/(num_tints+1)), 100)
            exp_table.append(colors)

            # KDTree előre felépítve nagy palettáknál
            if count > KDTREE_THRESHOLD:
                tree_table.append(cKDTree(colors.astype(np.float32)))
            else:
                tree_table.append(None)

        _lut.append(exp_table)
        _kdtrees.append(tree_table)

    _ready = True


def ensure_palettes():
    global _ready
    if not _ready:
        init_palettes()


def _exp_idx(values_per_segment: int) -> int:
    return max(0, min((INT_BITS // values_per_segment) - 1, INT_BITS - 1))


def get_color(palette: Palette, values_per_segment: int, index: int):
    ensure_palettes()
    table = _lut[int(palette)][_exp_idx(values_per_segment)]
    index = max(0, min(index, len(table) - 1))
    r, g, b = table[index]
    return int(r), int(g), int(b)


def color_to_id_value(color, palette: Palette, values_per_segment: int) -> int:
    ensure_palettes()
    r, g, b = int(color[0]), int(color[1]), int(color[2])
    ei    = _exp_idx(values_per_segment)
    table = _lut[int(palette)][ei]
    count = len(table)

    if palette == Palette.GRAYSCALE:
        lum = 0.299*r + 0.587*g + 0.114*b
        return min(count - 1, int(lum / (255.0 / count)))

    tree = _kdtrees[int(palette)][ei]
    if tree is not None:
        _, idx = tree.query(np.array([[r, g, b]], dtype=np.float32))
        return int(idx[0])

    diff = np.abs(table.astype(np.int32) - np.array([r, g, b], dtype=np.int32))
    return int(np.argmin(diff.sum(axis=1)))


def image_to_indices_vectorized(
    rgb_pixels: np.ndarray,
    palette: Palette,
    values_per_segment: int,
) -> np.ndarray:
    ensure_palettes()
    ei    = _exp_idx(values_per_segment)
    table = _lut[int(palette)][ei]
    count = len(table)
    N     = len(rgb_pixels)

    if palette == Palette.GRAYSCALE:
        lum = (0.299 * rgb_pixels[:, 0].astype(np.float32) +
               0.587 * rgb_pixels[:, 1].astype(np.float32) +
               0.114 * rgb_pixels[:, 2].astype(np.float32))
        return np.clip((lum / (255.0 / count)).astype(np.int32), 0, count - 1)

    # COLOR
    tree = _kdtrees[int(palette)][ei]
    if tree is not None:
        # Nagy paletta: KDTree — nincs memória-robbanás, O(N log K)
        _, indices = tree.query(rgb_pixels.astype(np.float32), workers=-1)
        return indices.astype(np.int32)

    # Kis paletta: numpy batch broadcasting
    BATCH   = 4096
    indices = np.empty(N, dtype=np.int32)
    tbl_i32 = table.astype(np.int32)

    for start in range(0, N, BATCH):
        end   = min(start + BATCH, N)
        chunk = rgb_pixels[start:end].astype(np.int32)
        diff  = np.abs(chunk[:, None, :] - tbl_i32[None, :, :]).sum(axis=2)
        indices[start:end] = np.argmin(diff, axis=1)

    return indices


def indices_to_image_vectorized(
    indices: np.ndarray,
    palette: Palette,
    values_per_segment: int,
    size: tuple,
) -> np.ndarray:
    ensure_palettes()
    table = _lut[int(palette)][_exp_idx(values_per_segment)]
    w, h  = size
    rgb   = table[np.clip(indices, 0, len(table)-1)]
    return rgb.reshape(h, w, 3)
