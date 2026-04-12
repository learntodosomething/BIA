import os, hmac, hashlib, base64, json
from PIL import Image as PilImage

SALT_SIZE = 32

# ── Magic byte-ok ────────────────────────────────────────────────────────────
MAGIC_BID_PLAIN  = b"BU"   # BID Unencrypted
MAGIC_BID_ENC    = b"BE"   # BID Encrypted
MAGIC_TOK_PLAIN  = b"TU"   # Token Unencrypted
MAGIC_TOK_ENC    = b"TE"   # Token Encrypted


# ══════════════════════════════════════════════════════════
#  CRYPTO PRIMITÍVEK
# ══════════════════════════════════════════════════════════
def _pbkdf2_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=salt, iterations=390_000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """salt(32) + Fernet-titkosított adat."""
    from cryptography.fernet import Fernet
    salt = os.urandom(SALT_SIZE)
    return salt + Fernet(_pbkdf2_key(password, salt)).encrypt(data)


def decrypt_bytes(data: bytes, password: str) -> bytes:
    """Raises cryptography.fernet.InvalidToken ha rossz a jelszó."""
    from cryptography.fernet import Fernet
    salt = data[:SALT_SIZE]
    return Fernet(_pbkdf2_key(password, salt)).decrypt(data[SALT_SIZE:])


# ══════════════════════════════════════════════════════════
#  HASH MASZKOLÁS
# ══════════════════════════════════════════════════════════
def compute_real_hash(img: PilImage.Image) -> str:
    return hashlib.sha256(img.convert("RGB").tobytes()).hexdigest()


def mask_hash(real_hash: str, password: str, salt: bytes) -> str:
    key    = password.encode() + salt
    mask   = hmac.new(key, real_hash.encode(), hashlib.sha256).digest()
    rh_b   = bytes.fromhex(real_hash)
    masked = bytes(a ^ b for a, b in zip(rh_b, mask))
    return masked.hex()


# ══════════════════════════════════════════════════════════
#  HASH BUNDLE
# ══════════════════════════════════════════════════════════
def make_hash_bundle(real_hash: str, password: str | None) -> bytes:
    if not password:
        return json.dumps({"hash": real_hash, "locked": False}).encode()
    salt      = os.urandom(SALT_SIZE)
    masked    = mask_hash(real_hash, password, salt)
    inner     = json.dumps({"hash": real_hash, "salt_hex": salt.hex()}).encode()
    encrypted = encrypt_bytes(inner, password)
    bundle = {
        "locked":      True,
        "masked_hash": masked,
        "salt_hex":    salt.hex(),
        "encrypted":   base64.b64encode(encrypted).decode(),
    }
    return json.dumps(bundle, indent=2).encode()


def open_hash_bundle(data: bytes, password: str | None) -> str:
    bundle = json.loads(data.decode())
    if not bundle.get("locked"):
        return bundle["hash"]
    if not password:
        raise ValueError("This hash file is password-protected.")
    encrypted = base64.b64decode(bundle["encrypted"])
    inner_raw = decrypt_bytes(encrypted, password)
    return json.loads(inner_raw.decode())["hash"]


def get_public_masked_hash(data: bytes) -> str:
    bundle = json.loads(data.decode())
    if not bundle.get("locked"):
        return bundle["hash"]
    return bundle.get("masked_hash", "???")


# ══════════════════════════════════════════════════════════
#  BID FÁJL I/O  (magic-byte alapú lock detection)
# ══════════════════════════════════════════════════════════
def save_bid(path: str, image_id, password: str | None, fmt: str = "zlib"):
    """
    BID mentés egyertelmű magic-byte fejléccel.
    fmt: 'zlib' | 'lzma' | 'raw'
    """
    payload = image_id.to_bytes(fmt=fmt)
    if password:
        with open(path, "wb") as f:
            f.write(MAGIC_BID_ENC + encrypt_bytes(payload, password))
    else:
        with open(path, "wb") as f:
            f.write(MAGIC_BID_PLAIN + payload)


def is_bid_encrypted(path: str) -> bool:
    """Megbizható detekció: az elso 2 bajt alapjan."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == MAGIC_BID_ENC
    except Exception:
        return False


def load_bid(path: str, password: str | None):
    """
    BID betöltés. Automatikusan detektálja hogy titkosított-e.
    Ha titkosított és nincs jelszó megadva → ValueError.
    Ha rossz jelszó → InvalidToken.
    """
    from engine.id_codec import ImageID
    with open(path, "rb") as f:
        raw = f.read()

    magic   = raw[:2]
    payload = raw[2:]

    if magic == MAGIC_BID_ENC:
        if not password:
            raise ValueError("ENCRYPTED")
        payload = decrypt_bytes(payload, password)
    elif magic == MAGIC_BID_PLAIN:
        pass  # payload mar helyes
    else:
        # Regi formatum visszafele kompatibilitas
        payload = raw

    try:
        return ImageID.from_bytes(payload)
    except Exception:
        try:
            return ImageID.from_string(payload.decode("utf-8"))
        except Exception:
            raise ValueError("Cannot parse BID (invalid format or wrong password)")


# ══════════════════════════════════════════════════════════
#  TOKEN FÁJL I/O  (magic-byte alapú lock detection)
# ══════════════════════════════════════════════════════════
def save_token_file(path: str, token: str, password: str | None):
    """Token mentés egyertelmű magic-byte fejléccel."""
    data = token.encode("utf-8")
    if password:
        with open(path, "wb") as f:
            f.write(MAGIC_TOK_ENC + encrypt_bytes(data, password))
    else:
        with open(path, "wb") as f:
            f.write(MAGIC_TOK_PLAIN + data)


def is_token_encrypted(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == MAGIC_TOK_ENC
    except Exception:
        return False


def load_token_file(path: str, password: str | None) -> str:
    """
    Token betöltés fájlból. Automatikusan detektálja hogy titkosított-e.
    """
    with open(path, "rb") as f:
        raw = f.read()

    magic   = raw[:2]
    payload = raw[2:]

    if magic == MAGIC_TOK_ENC:
        if not password:
            raise ValueError("ENCRYPTED")
        payload = decrypt_bytes(payload, password)
    elif magic == MAGIC_TOK_PLAIN:
        pass
    else:
        # Regi formatum: sima UTF-8 szoveg (elso ket bajt nem magic)
        payload = raw

    return payload.decode("utf-8").strip()


# ══════════════════════════════════════════════════════════
#  HASH FÁJL I/O
# ══════════════════════════════════════════════════════════
def save_hash_file(path: str, real_hash: str, password: str | None):
    bundle_bytes = make_hash_bundle(real_hash, password)
    with open(path, "wb") as f:
        f.write(bundle_bytes)


def load_hash_file(path: str, password: str | None) -> str:
    with open(path, "rb") as f:
        data = f.read()
    return open_hash_bundle(data, password)


def load_public_masked_hash(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    try:
        return get_public_masked_hash(data)
    except Exception:
        return "(cannot read)"


def is_hash_locked(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            data = f.read()
        bundle = json.loads(data.decode())
        return bundle.get("locked", False)
    except Exception:
        return True


# ── Visszafele kompatibilis heurisztika (csak ha nincs magic) ────────────────
def _is_binary(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return not all(32 <= b < 127 for b in header)
    except Exception:
        return True
