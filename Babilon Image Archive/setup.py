import sys
import subprocess
import importlib

# ── Szükséges csomagok ──────────────────────────────────────────────────────
#  (csomagnév, import-név, opcionális-e)
REQUIRED = [
    ("PyQt6",            "PyQt6",             False),
    ("Pillow",           "PIL",               False),
    ("numpy",            "numpy",             False),
    ("cryptography",     "cryptography",      False),
]

OPTIONAL = [
    # AI generáláshoz — GPU szükséges, nagy letöltés
    ("torch",            "torch",             True),
    ("diffusers",        "diffusers",         True),
    ("transformers",     "transformers",      True),
    ("accelerate",       "accelerate",        True),
    ("huggingface_hub",  "huggingface_hub",   True),
]


def _pip_install(package: str) -> bool:
    """Returns True if install succeeded."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_installed(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def check_and_install(progress_callback=None):
    """
    Ellenőrzi és telepíti a hiányzó csomagokat.
    progress_callback(msg: str) — ha megadod, kiírja az állapotot.

    Returns: (all_required_ok: bool, missing_optional: list[str])
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    missing_required = []
    missing_optional = []

    # ── Kötelező csomagok ───────────────────────────────
    for pkg, imp, _ in REQUIRED:
        if not _is_installed(imp):
            log(f"Telepítés: {pkg}…")
            if _pip_install(pkg):
                log(f"  ✓ {pkg} telepítve")
            else:
                log(f"  ✗ {pkg} telepítése SIKERTELEN")
                missing_required.append(pkg)
        else:
            log(f"  ✓ {pkg} OK")

    # ── Opcionális csomagok ──────────────────────────────
    for pkg, imp, _ in OPTIONAL:
        if not _is_installed(imp):
            missing_optional.append(pkg)

    return len(missing_required) == 0, missing_optional


def install_ai_packages(progress_callback=None):
    """Telepíti az AI csomagokat (torch stb.) — csak ha a felhasználó kéri."""
    def log(msg):
        if progress_callback: progress_callback(msg)
        else: print(msg)

    # torch: CUDA verziót próbáljuk először
    if not _is_installed("torch"):
        log("Torch telepítése (CUDA 12.1)…")
        ok = _pip_install(
            "torch torchvision --index-url https://download.pytorch.org/whl/cu121"
        )
        if not ok:
            log("CUDA verzió sikertelen, CPU verzió telepítése…")
            _pip_install("torch torchvision")

    for pkg, imp, _ in OPTIONAL[1:]:   # diffusers, transformers, accelerate, hf_hub
        if not _is_installed(imp):
            log(f"Telepítés: {pkg}…")
            _pip_install(pkg)
            log(f"  ✓ {pkg}")


if __name__ == "__main__":
    print("=== BABYLON DEPENDENCY CHECK ===")
    ok, missing = check_and_install()
    if not ok:
        print("\nHIBA: Kötelező csomagok hiányoznak!")
        sys.exit(1)
    if missing:
        print(f"\nOpcionális (AI) csomagok hiányoznak: {missing}")
        print("Az AI generálás nem lesz elérhető ezek nélkül.")
    print("\nMindes rendben, az alkalmazás indítható.")
