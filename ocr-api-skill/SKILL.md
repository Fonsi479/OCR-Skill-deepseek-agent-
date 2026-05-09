---
name: ocr-api
description: Use SiliconFlow PaddleOCR-VL-1.5 to extract text from images, screenshots, scanned documents, tables, formulas, or PDF page images. No heavy dependencies — uses direct HTTP API calls. API key auto-loaded from ~/Documents/.siliconflow_key or env var.
---

# SiliconFlow PaddleOCR-VL OCR

## Overview

Use SiliconFlow's hosted PaddleOCR-VL model for OCR and document parsing when the active agent cannot read image text directly. Supports images (PNG, JPG, WEBP, GIF, BMP, TIFF) and PDFs (via PyMuPDF).

**API Key Auto-Discovery** (checked in order):
1. `SILICONFLOW_API_KEY` environment variable
2. `~/.siliconflow_key`
3. `~/Documents/.siliconflow_key`
4. `/tmp/.siliconflow_key`
5. Mounted workspace folders under `/sessions/*/mnt/**/` (VM sandbox — auto-detected)

Once saved (e.g., to `~/Documents/.siliconflow_key`), no manual setup needed on subsequent runs.

## Usage (for Cowork)

### Step 1 — Write the OCR script to /tmp

The script writes to `/tmp/ocr_api.py`. A version header ensures stale cached copies are always refreshed.

```bash
SCRIPT_VER="# ocr-api v2"
if [ "$(head -1 /tmp/ocr_api.py 2>/dev/null)" != "$SCRIPT_VER" ]; then
  cat > /tmp/ocr_api.py << 'PYEOF'
# ocr-api v2
import sys, os, re, base64, json, time, tempfile, urllib.request
from pathlib import Path

API_KEY_ENV = "SILICONFLOW_API_KEY"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_TOKENS = 8192

def _get_key():
    k = os.environ.get(API_KEY_ENV, "").strip()
    if k: return k
    candidates = [
        Path.home() / ".siliconflow_key",
        Path.home() / "Documents" / ".siliconflow_key",
        Path("/tmp/.siliconflow_key"),
    ]
    sessions_root = Path("/sessions")
    if sessions_root.exists():
        try:
            for p in sorted(sessions_root.glob("*/.siliconflow_key")):
                candidates.append(p)
            for p in sorted(sessions_root.glob("*/mnt/**/.siliconflow_key")):
                candidates.append(p)
        except (PermissionError, OSError):
            pass
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.read_text().strip()
        except (PermissionError, OSError):
            continue
    print("Error: SILICONFLOW_API_KEY not set.", file=sys.stderr)
    print("Save your key to ~/Documents/.siliconflow_key or set the env var.", file=sys.stderr)
    print("Get a free key: https://cloud.siliconflow.cn/account/ak", file=sys.stderr)
    sys.exit(1)

_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".tif": "image/tiff",
}

def _ocr_image(file_path, api_key, timeout=120, max_image_bytes=MAX_IMAGE_BYTES):
    file_size = os.path.getsize(file_path)
    if file_size > max_image_bytes:
        raise ValueError(f"Image too large ({file_size/1024/1024:.1f} MB). Max: {max_image_bytes/1024/1024:.0f} MB. Reduce DPI or use --max-image-mb to increase limit.")
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    ext = Path(file_path).suffix.lower()
    data_url = f"data:{_MIME.get(ext, 'image/png')};base64,{b64}"
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": (
                "请识别并提取这张图片中的所有文字内容，保持原有格式。"
                "Please extract all text from this image, preserving the original formatting."
            )},
        ]}],
        "max_tokens": MAX_TOKENS,
    }).encode()
    req = urllib.request.Request(API_URL, data=payload, headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    })
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())["choices"][0]["message"]["content"]

def _call_with_retry(file_path, api_key, timeout=120, max_image_bytes=MAX_IMAGE_BYTES):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _ocr_image(file_path, api_key, timeout=timeout, max_image_bytes=max_image_bytes)
        except ValueError:
            raise
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (2 ** (attempt - 1))
                print(f"[ocr_api] Retry {attempt}/{MAX_RETRIES} after {delay}s: {e}", file=sys.stderr)
                time.sleep(delay)
    raise last_error

def _pdf_to_images(pdf_path, dpi=200):
    try: import fitz
    except ImportError:
        import subprocess
        print("[ocr_api] Installing PyMuPDF for PDF support...", file=sys.stderr)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "PyMuPDF"])
        import fitz
    tmpdir = tempfile.mkdtemp(prefix="ocr_pdf_")
    paths = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF: {e}. File may be corrupted or not a valid PDF.")
    try:
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(dpi=dpi)
            p = os.path.join(tmpdir, f"page_{i+1}.png")
            pix.save(p); paths.append(p)
    finally:
        doc.close()
    print(f"[ocr_api] PDF: {len(paths)} page(s) @ {dpi} DPI", file=sys.stderr)
    return paths, tmpdir

def _clean(t):
    if t is None:
        return ""
    t = re.sub(r"<\|LOC_\d+(?:_\d+)?\|>", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r" +\n", "\n", t)
    return t.strip()

def main():
    import argparse
    p = argparse.ArgumentParser(description="OCR via SiliconFlow PaddleOCR-VL")
    p.add_argument("file_path")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--raw", action="store_true")
    p.add_argument("--format", choices=("text","json"), default="text")
    p.add_argument("--max-image-mb", type=float, default=20.0)
    args = p.parse_args()
    fp = Path(args.file_path)
    if not fp.exists():
        print(f"Error: file not found: {args.file_path}", file=sys.stderr); sys.exit(1)
    api_key = _get_key()
    ext = fp.suffix.lower()
    pdf_tmpdir = None
    if ext == ".pdf":
        image_paths, pdf_tmpdir = _pdf_to_images(str(fp), dpi=args.dpi)
    elif ext in _MIME:
        image_paths = [str(fp)]
    else:
        print(f"Error: unsupported type '{ext}'. Supported: {', '.join(sorted(_MIME.keys()))}, .pdf", file=sys.stderr)
        sys.exit(1)
    results = []
    errors = []
    max_image_bytes = int(args.max_image_mb * 1024 * 1024)
    try:
        for i, img_path in enumerate(image_paths):
            if len(image_paths) > 1:
                print(f"[ocr_api] Page {i+1}/{len(image_paths)} ...", file=sys.stderr)
            try:
                raw = _call_with_retry(img_path, api_key, timeout=args.timeout, max_image_bytes=max_image_bytes)
                results.append((i+1, raw if args.raw else _clean(raw)))
            except Exception as e:
                errors.append((i+1, str(e)))
                print(f"[ocr_api] Error on page {i+1}: {e}", file=sys.stderr)
        if errors and not results:
            print(f"[ocr_api] All pages failed.", file=sys.stderr); sys.exit(2)
    finally:
        if pdf_tmpdir:
            import shutil
            try: shutil.rmtree(pdf_tmpdir)
            except: pass
    if args.format == "json":
        output = [{"page": p, "text": t} for p, t in results]
        print(json.dumps(output if len(output) > 1 else output[0], ensure_ascii=False, indent=2))
    else:
        for p, t in results:
            if len(image_paths) > 1: print(f"\n--- Page {p} ---")
            print(t)

if __name__ == "__main__":
    main()
PYEOF
fi
```

### Step 2 — Run OCR (no manual key needed)

```bash
python3 /tmp/ocr_api.py "$FILE_PATH"
```

**Supported file types:** PNG, JPG, JPEG, WEBP, GIF, BMP, TIFF, PDF

**Options:**
- `--dpi 300` — Higher DPI for PDF rendering (default: 200)
- `--raw` — Skip post-processing cleanup
- `--format json` — Output as JSON instead of plain text
- `--timeout 120` — API timeout in seconds
- `--max-image-mb 30` — Increase image size limit (default: 20 MB) for high-DPI scans

### Step 3 — Use the Output

The script prints cleaned text to stdout. Read the OCR result and use it for the downstream task.

## One-Time Setup

Save your API key once and the script finds it automatically:

```bash
echo "YOUR_API_KEY_HERE" > ~/Documents/.siliconflow_key
```

Or via environment variable:

```bash
echo 'export SILICONFLOW_API_KEY="YOUR_API_KEY_HERE"' >> ~/.zshrc
```

Get a free key at: https://cloud.siliconflow.cn/account/ak

## Post-processing Rules

1. Use the OCR output as the source text — do not invent missing text.
2. If OCR marks unclear characters as `?`, preserve them as-is.
3. For lab reports, formulas, tables, and experiment guides:
   - Keep original units and symbols
   - Keep formulas in LaTeX when possible (e.g., `$E = mc^2$`)
   - Output tables as Markdown tables when recognizable
   - Mark uncertain recognition with `?`
4. If the OCR result is poor, suggest cropping, increasing DPI, or switching to a clearer PNG image.
5. The script automatically cleans `<|LOC_N|>` position markers from the output.
6. Whitespace is normalized (multiple blank lines collapsed, trailing spaces stripped) but table alignment spaces are preserved.

## Error Handling

| Situation | Action |
|-----------|--------|
| API 403/401 error | Verify API key is valid and has PaddleOCR-VL access |
| File not found | Verify the file path with the user |
| PyMuPDF install fails | Run: `pip install --break-system-packages PyMuPDF` |
| PDF too large | Suggest extracting specific pages as images first |
| API key missing | Set `SILICONFLOW_API_KEY` env var or save key to `~/Documents/.siliconflow_key` |
| Image > 20 MB | Script rejects with a clear error; use `--max-image-mb 30` to raise the limit, or reduce DPI |
| Transient API failure | Script retries up to 3 times with exponential backoff (2s→4s→8s) |
| PDF page fails mid-batch | Error logged for that page; successful pages are preserved |
| Corrupted PDF | Clear error message: file may be corrupted or not a valid PDF |

## Standalone Script

For batch processing or file output:

```bash
python3 scripts/ocr_paddleocr_vl.py --input ./document.pdf --output ./ocr-output
```

Run `python3 scripts/ocr_paddleocr_vl.py --help` for all options.
