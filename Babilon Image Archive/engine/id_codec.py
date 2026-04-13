import math, zlib, base64, struct, random
from typing import List


INT_BITS    = 15
VALID_LOWER = ord(' ')

# Image Token fejléc (4 bájt magic)
TOKEN_MAGIC = b'BIT1'   # Babylon Image Token v1


class Segment:
    def __init__(self, value: int = 0):
        self.value = value & ((1 << INT_BITS) - 1)

    def set_sub(self, bit_offset: int, bit_count: int, val: int):
        mask = ((1 << (bit_offset + bit_count)) - 1) - ((1 << bit_offset) - 1)
        self.value &= ((1 << INT_BITS) - 1) - mask
        self.value |= (int(val) << bit_offset) & mask

    def get_sub(self, bit_offset: int, bit_count: int) -> int:
        mask = (1 << (bit_offset + bit_count)) - 1
        return (self.value & mask) >> bit_offset


class ImageID:
    MAX_VALUES_PER_SEGMENT = INT_BITS  # 15

    def __init__(self, value_count: int = 0, values_per_segment: int = 2):
        self.values_per_segment = max(1, min(values_per_segment, self.MAX_VALUES_PER_SEGMENT))
        self.value_count        = value_count
        self.palette_index      = 0
        self.size               = (0, 0)
        seg_count = max(1, math.ceil(value_count / self.values_per_segment))
        self._segments: List[Segment] = [Segment() for _ in range(seg_count)]

    # ── value access ────────────────────────────────────────────────────
    def set_value(self, index: int, value: int):
        si  = index // self.values_per_segment
        off = (index % self.values_per_segment) * self._bits_per_value()
        self._segments[si].set_sub(off, self._bits_per_value(), value)

    def get_value(self, index: int) -> int:
        si  = index // self.values_per_segment
        off = (index % self.values_per_segment) * self._bits_per_value()
        return self._segments[si].get_sub(off, self._bits_per_value())

    def randomise(self):
        for seg in self._segments:
            seg.value = random.randint(0, (1 << INT_BITS) - 1)

    def _bits_per_value(self) -> int:
        return INT_BITS // self.values_per_segment

    # ── Binary serialization (compact) ──────────────────────────────────
    def to_bytes(self, fmt: str = "zlib") -> bytes:
        """
        Bináris formátum, fmt szerinti tömörítéssel:
          fmt="zlib"  – zlib level 9 (alapértelmezett, gyors)
          fmt="lzma"  – lzma preset 9 (jobb arány, lassabb)
          fmt="raw"   – tömörítés nélkül

        Struktúra tömörítés előtt:
          4B  magic  "BIT1"
          2B  width  (uint16 LE)
          2B  height (uint16 LE)
          1B  values_per_segment
          1B  palette_index
          4B  seg_count (int32 LE)
          N*2B segment values (uint16 LE)
        """
        w, h = self.size
        header = TOKEN_MAGIC
        header += struct.pack('<HHBBi',
            w, h,
            self.values_per_segment,
            self.palette_index,
            len(self._segments),
        )
        seg_data = struct.pack(f'<{len(self._segments)}H',
                               *[s.value for s in self._segments])
        raw = header + seg_data

        # 1 bájt prefix jelzi a kompressziós módot
        if fmt == "lzma":
            import lzma
            return b'L' + lzma.compress(raw, preset=9)
        elif fmt == "raw":
            return b'R' + raw
        else:  # zlib (default)
            return b'Z' + zlib.compress(raw, level=9)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ImageID':
        # Első bájt = kompressziós mód jelzője
        if len(data) < 1:
            raise ValueError("Empty data")
        mode = data[0:1]
        payload = data[1:]
        if mode == b'L':
            import lzma
            raw = lzma.decompress(payload)
        elif mode == b'R':
            raw = payload
        elif mode == b'Z':
            raw = zlib.decompress(payload)
        else:
            # Régi formátum: nincs prefix, zlib az egész
            raw = zlib.decompress(data)
        magic = raw[:4]
        if magic != TOKEN_MAGIC:
            raise ValueError(f"Bad magic: {magic!r}")
        w, h, vps, pal, seg_count = struct.unpack_from('<HHBBi', raw, 4)
        seg_offset = 4 + struct.calcsize('<HHBBi')
        seg_values = struct.unpack_from(f'<{seg_count}H', raw, seg_offset)

        obj = cls.__new__(cls)
        obj.values_per_segment = vps
        obj.palette_index      = pal
        obj.size               = (w, h)
        obj._segments          = [Segment(v) for v in seg_values]
        obj.value_count        = seg_count * vps
        return obj

    # ── Image Token (base85 text, self-contained) ────────────────────────
    def to_token(self) -> str:
        """
        Szöveges, önállóan megosztható token.
        base85-kódolt tömörített bináris.
        Egy 320×180 / vps=2 kép ~tipikusan 8-15 KB szöveg.
        Beilleszthető chat-be, szövegfájlba, bárhova.
        """
        return base64.b85encode(self.to_bytes()).decode('ascii')

    @classmethod
    def from_token(cls, token: str) -> 'ImageID':
        """Token szövegből visszaállítja az ImageID-t."""
        token = token.strip()
        raw_compressed = base64.b85decode(token.encode('ascii'))
        return cls.from_bytes(raw_compressed)

    # ── File I/O ────────────────────────────────────────────────────────
    def save(self, path: str):
        """BID fájl mentése (bináris, tömörített)."""
        with open(path, 'wb') as f:
            f.write(self.to_bytes())

    @classmethod
    def load(cls, path: str) -> 'ImageID':
        """BID fájl betöltése."""
        with open(path, 'rb') as f:
            return cls.from_bytes(f.read())

    # ── Legacy string (kept for compatibility) ───────────────────────────
    def to_string(self) -> str:
        """Régi szöveges formátum — csak visszafelé kompatibilitáshoz."""
        chars = [
            chr(self.size[0] + VALID_LOWER),
            chr(self.size[1] + VALID_LOWER),
            chr(self.values_per_segment + VALID_LOWER),
            chr(self.palette_index + VALID_LOWER),
        ]
        for seg in self._segments:
            chars.append(chr(seg.value + VALID_LOWER))
        return ''.join(chars)

    @classmethod
    def from_string(cls, s: str) -> 'ImageID':
        """Régi szöveges formátum betöltése."""
        if len(s) < 4:
            raise ValueError("ID string too short")
        w   = ord(s[0]) - VALID_LOWER
        h   = ord(s[1]) - VALID_LOWER
        vps = ord(s[2]) - VALID_LOWER
        pal = ord(s[3]) - VALID_LOWER
        obj = cls.__new__(cls)
        obj.values_per_segment = vps
        obj.palette_index      = pal
        obj.size               = (w, h)
        obj._segments          = [Segment(ord(c) - VALID_LOWER) for c in s[4:]]
        obj.value_count        = len(obj._segments) * vps
        return obj
