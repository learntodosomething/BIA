import os
from pathlib import Path

MODEL_DIR      = Path("models")
MODEL_FILENAME = "image.safetensors"
MODEL_PATH     = MODEL_DIR / MODEL_FILENAME
HF_REPO_ID     = "Lagyo/ImgenBasic"


def model_exists() -> bool:
    return MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1_000_000


def download_model(progress_callback=None) -> Path:
    def log(msg):
        if progress_callback: progress_callback(msg)
        else: print(msg)

    if model_exists():
        log(f"✓ Modell megtalálva: {MODEL_PATH}")
        return MODEL_PATH

    log(f"Modell hiányzik: {MODEL_PATH}")
    log("Letöltés a HuggingFace-ről…")
    log(f"  Repo: {HF_REPO_ID}")
    log(f"  Fájl: {MODEL_FILENAME}")
    log("  Ez eltarthat néhány percig a fájl méretétől függően…")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        log("huggingface_hub nem telepített, telepítés…")
        import subprocess, sys
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "huggingface_hub", "--quiet"],
            check=True
        )
        from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=HF_REPO_ID,
        filename=MODEL_FILENAME,
        local_dir=str(MODEL_DIR),
        local_dir_use_symlinks=False,
    )

    log(f"✓ Modell letöltve: {path}")
    return Path(path)


def ensure_model(progress_callback=None) -> Path | None:
    try:
        return download_model(progress_callback)
    except Exception as e:
        if progress_callback:
            progress_callback(f"Modell letöltés sikertelen: {e}")
        return None
