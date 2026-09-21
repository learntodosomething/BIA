# Babylon Image Archive (BIA)

**Image identification and data transfer using hash-based representation**

BIA is a Python system that converts images into a compact, shareable **Image Token** (text string) instead of transferring traditional image files (JPEG/PNG).  
The token can later be decoded back into an image or used together with a diffusion model.

This project was developed as a Master's thesis at J. Selye University (2026).

## Key Features

- **BID (Babylon Image Data)** format  
  Palette-based quantization + bit-packing into 15-bit segments + zlib/lzma compression.

- **Image Token**  
  A single text string that represents the image and can be shared without sending the original file.

- **Two-layer cryptography**  
  - AES-128 encryption (Fernet + PBKDF2)  
  - HMAC-SHA256 based hash masking

- **Efficient palette quantization**  
  Based on `scipy.spatial.cKDTree` (memory-efficient and deterministic for `values_per_segment` 1–15).

- **AI image generation**  
  Integrated diffusion model with automatic hardware detection (CUDA / MPS / CPU) and background inference.

## Main Results (from thesis)

| Metric                        | Result                          |
|------------------------------|---------------------------------|
| Round-trip validation (BID)  | Successful on all tested configs |
| PSNR (vps=1, Color)          | ~38.2 dB (excellent quality)    |
| PSNR (vps=2, Color)          | ~31.5 dB (good quality)         |
| Quantization time (vps=1)    | ~810 ms (320×180, Color)        |
| Quantization time (vps=4)    | ~28 ms                          |
| Encryption (100 KB)          | ~5–6 ms                         |

Compression ratio strongly depends on image content (much better on structured / low-entropy images).

## Requirements

- Python 3.10+
- At least 8 GB VRAM recommended for comfortable AI generation
- 12 GB free disk space recommended when using the diffusion model

## Quick Start

```bash
git clone https://github.com/learntodosomething/BIA.git
cd BIA
# Install dependencies (see requirements or setup.py)
python main.py
