#!/usr/bin/env python3
"""OCR via SiliconFlow PaddleOCR-VL API — direct HTTP, no paddleocr dependency."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1/chat/completions"
DEFAULT_MODEL = "PaddlePaddle/PaddleOCR-VL-1.5"
API_KEY_ENV = "SILICONFLOW_API_KEY"
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_MAX_TOKENS = 8192
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds base, exponential backoff

_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".tif": "image/tiff",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract OCR text from images or PDFs with SiliconFlow PaddleOCR-VL.",
    )
    parser.add_argument("--input", required=True, help="Input image/PDF path or URL.")
    parser.add_argument(
        "--output",
        help=(
            "Output file or directory. Directories are recommended for PDFs. "
            "If omitted, output is printed to stdout."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format: text (plain, default), json, or markdown.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"SiliconFlow model name. Defaults to {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible chat completions URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="API timeout in seconds. Defaults to 120.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for PDF page rendering. Defaults to 200.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip post-processing cleanup (including <|LOC_N|> marker removal).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max tokens for API response. Defaults to {DEFAULT_MAX_TOKENS}.",
    )
    parser.add_argument(
        "--max-image-mb",
        type=float,
        default=20.0,
        help="Maximum image file size in MB before rejection. Defaults to 20. Increase for high-DPI scans.",
    )
    parser.add_argument(
        "--pages",
        help="Page range for PDFs (e.g. '1,3-5' or '2'). Ignored for non-PDF inputs.",
    )
    return parser.parse_args()


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _get_api_key() -> str:
    """Get API key from env var or fallback key files (auto-discovery)."""
    key = os.environ.get(API_KEY_ENV, "").strip()
    if key:
        return key
    # Auto-discovery: check multiple known locations
    candidates = [
        Path.home() / ".siliconflow_key",
        Path.home() / "Documents" / ".siliconflow_key",
        Path("/tmp/.siliconflow_key"),
    ]
    # Also search VM sandbox mounted paths (so it works in Cowork sessions)
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

    raise SystemExit(
        f"Missing API key. Save it to ~/Documents/.siliconflow_key or set the {API_KEY_ENV} env var:\n"
        f"  export {API_KEY_ENV}=\"your_api_key_here\"\n"
        "Get a free key: https://cloud.siliconflow.cn/account/ak"
    )


def validate_input(input_value: str) -> None:
    if is_url(input_value):
        return
    input_path = Path(input_value).expanduser()
    if not input_path.exists():
        raise SystemExit(f"Input does not exist: {input_path}")
    if not input_path.is_file():
        raise SystemExit(f"Input must be a file or URL: {input_path}")


def _ocr_image(file_path: str, api_key: str, model: str, base_url: str,
               timeout: int = 120, max_tokens: int = DEFAULT_MAX_TOKENS,
               max_image_bytes: int = MAX_IMAGE_BYTES) -> str:
    """Call SiliconFlow PaddleOCR-VL API with an image file."""
    file_size = os.path.getsize(file_path)
    if file_size > max_image_bytes:
        raise ValueError(
            f"Image too large ({file_size / 1024 / 1024:.1f} MB). "
            f"Maximum is {max_image_bytes / 1024 / 1024:.0f} MB. "
            "Reduce DPI (--dpi) or increase limit (--max-image-mb)."
        )

    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    ext = Path(file_path).suffix.lower()
    mime = _MIME.get(ext, "image/png")
    data_url = f"data:{mime};base64,{b64}"

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": (
                "请识别并提取这张图片中的所有文字内容，保持原有格式。"
                "Please extract all text from this image, preserving the original formatting."
            )},
        ]}],
        "max_tokens": max_tokens,
    }).encode()

    req = urllib.request.Request(
        base_url, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_with_retry(file_path: str, api_key: str, model: str, base_url: str,
                     timeout: int = 120, max_tokens: int = DEFAULT_MAX_TOKENS,
                     max_image_bytes: int = MAX_IMAGE_BYTES) -> str:
    """Call OCR with exponential backoff retry on transient failures."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _ocr_image(file_path, api_key, model, base_url,
                              timeout=timeout, max_tokens=max_tokens,
                              max_image_bytes=max_image_bytes)
        except ValueError:
            raise  # Do not retry client errors (e.g. image too large)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (2 ** (attempt - 1))
                print(f"[ocr_api] Retry {attempt}/{MAX_RETRIES} after {delay}s: {e}",
                      file=sys.stderr)
                time.sleep(delay)
    raise last_error


def _parse_pages(pages_arg: str | None, total_pages: int) -> list[int]:
    """Parse a page range string like '1,3-5' into a sorted list of 1-based page indices."""
    if pages_arg is None:
        return list(range(1, total_pages + 1))
    result: set[int] = set()
    for part in pages_arg.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    # Filter to valid range, sort
    return sorted(p for p in result if 1 <= p <= total_pages)


def _pdf_to_images(pdf_path: str, dpi: int = 200,
                   pages: list[int] | None = None) -> tuple[list[str], str]:
    """Convert PDF pages to PNG images using PyMuPDF.

    Returns (list of image paths, temp directory path).
    The caller is responsible for cleaning up the temp directory.
    """
    try:
        import fitz  # type: ignore
    except ImportError:
        import subprocess
        print("[ocr_api] Installing PyMuPDF for PDF support...", file=sys.stderr)
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--break-system-packages", "--quiet", "PyMuPDF",
        ])
        import fitz  # type: ignore

    tmpdir = tempfile.mkdtemp(prefix="ocr_pdf_")
    paths: list[str] = []

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(
            f"Failed to open PDF '{pdf_path}': {e}. "
            "File may be corrupted or not a valid PDF."
        ) from e

    total = len(doc)
    target_pages = pages if pages is not None else list(range(1, total + 1))

    try:
        for pnum in target_pages:
            if pnum < 1 or pnum > total:
                print(f"[ocr_api] Skipping out-of-range page {pnum} (PDF has {total} pages)",
                      file=sys.stderr)
                continue
            pix = doc[pnum - 1].get_pixmap(dpi=dpi)
            out = os.path.join(tmpdir, f"page_{pnum}.png")
            pix.save(out)
            paths.append(out)
    finally:
        doc.close()

    print(f"[ocr_api] PDF: {len(paths)} page(s) @ {dpi} DPI", file=sys.stderr)
    return paths, tmpdir


def _clean(text: str | None) -> str:
    """Remove LOC markers and normalise whitespace without destroying formatting."""
    if text is None:
        return ""
    text = re.sub(r"<\|LOC_\d+(?:_\d+)?\|>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


class OCRResult:
    """Minimal result wrapper for unified output handling."""

    def __init__(self, text: str, clean_text: str):
        self.text = text
        self.clean_text = clean_text

    def save_to_markdown(self, save_path: str) -> None:
        p = Path(save_path)
        content = self.clean_text
        if p.suffix:
            p.write_text(content, encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)
            (p / "result.md").write_text(content, encoding="utf-8")

    def save_to_json(self, save_path: str) -> None:
        p = Path(save_path)
        data = {"content": self.clean_text}
        if p.suffix:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)
            (p / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                           encoding="utf-8")

    def save_to_text(self, save_path: str) -> None:
        p = Path(save_path)
        if p.suffix:
            p.write_text(self.clean_text, encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)
            (p / "result.txt").write_text(self.clean_text, encoding="utf-8")


def run_prediction(input_value: str, api_key: str, model: str, base_url: str,
                   timeout: int = 120, dpi: int = 200, raw: bool = False,
                   max_tokens: int = DEFAULT_MAX_TOKENS,
                   max_image_bytes: int = MAX_IMAGE_BYTES,
                   pages: list[int] | None = None) -> list[OCRResult]:
    """Run OCR on an image or PDF, returning a list of results.

    Per-page errors are collected and reported but do not discard already-successful pages.
    """
    ext = Path(urlparse(input_value).path).suffix.lower()
    pdf_tmpdir: str | None = None

    if ext == ".pdf":
        image_paths, pdf_tmpdir = _pdf_to_images(input_value, dpi=dpi, pages=pages)
    elif ext in _MIME:
        image_paths = [input_value]
    else:
        supported = ", ".join(sorted(_MIME.keys()))
        raise SystemExit(
            f"Unsupported type '{ext}'. Supported: {supported}, .pdf"
        )

    results: list[OCRResult] = []
    errors: list[tuple[int, str]] = []

    try:
        for i, img_path in enumerate(image_paths):
            if len(image_paths) > 1:
                print(f"[ocr_api] Page {i+1}/{len(image_paths)} ...", file=sys.stderr)
            try:
                raw_text = _call_with_retry(
                    img_path, api_key, model, base_url,
                    timeout=timeout, max_tokens=max_tokens,
                    max_image_bytes=max_image_bytes,
                )
                clean_text = raw_text if raw else _clean(raw_text)
                results.append(OCRResult(text=raw_text, clean_text=clean_text))
            except Exception as e:
                errors.append((i + 1, str(e)))
                print(f"[ocr_api] Error on page {i+1}: {e}", file=sys.stderr)
                # Continue with remaining pages — don't discard prior results

        if errors and not results:
            raise SystemExit(
                f"All {len(errors)} page(s) failed. First error: {errors[0][1]}"
            )
        elif errors:
            print(
                f"[ocr_api] {len(errors)} page(s) failed: "
                + ", ".join(f"p.{p}" for p, _ in errors),
                file=sys.stderr,
            )
    finally:
        # Always clean up temp PDF images
        if pdf_tmpdir:
            try:
                import shutil
                shutil.rmtree(pdf_tmpdir)
            except Exception:
                pass

    return results


def sorted_outputs(directory: Path, output_format: str) -> list[Path]:
    if output_format == "json":
        pattern = "*.json"
    elif output_format == "markdown":
        pattern = "*.md"
    else:
        pattern = "*.txt"
    return sorted(path for path in directory.rglob(pattern) if path.is_file())


def emit_markdown(paths: Iterable[Path]) -> None:
    first = True
    for path in paths:
        if not first:
            print("\n\n---\n")
        first = False
        print(path.read_text(encoding="utf-8"))


def emit_text(paths: Iterable[Path]) -> None:
    first = True
    for path in paths:
        if not first:
            print("\n\n---\n")
        first = False
        print(path.read_text(encoding="utf-8"))


def emit_json(paths: Iterable[Path]) -> None:
    payload = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            payload.append(json.load(handle))
    if len(payload) == 1:
        print(json.dumps(payload[0], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def save_or_print(results: list[OCRResult], output_format: str,
                  output: str | None) -> None:
    if output:
        output_path = Path(output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix and len(results) > 1:
            with tempfile.TemporaryDirectory(prefix="ocr-vl-") as tmp:
                tmp_path = Path(tmp)
                for r in results:
                    if output_format == "markdown":
                        r.save_to_markdown(str(tmp_path))
                    elif output_format == "json":
                        r.save_to_json(str(tmp_path))
                    else:
                        r.save_to_text(str(tmp_path))
                generated = sorted_outputs(tmp_path, output_format)
                if output_format == "json":
                    merged = []
                    for p in generated:
                        with p.open("r", encoding="utf-8") as h:
                            merged.append(json.load(h))
                    output_path.write_text(
                        json.dumps(merged, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                else:
                    output_path.write_text(
                        "\n\n---\n\n".join(p.read_text(encoding="utf-8") for p in generated),
                        encoding="utf-8",
                    )
        else:
            if not output_path.suffix:
                output_path.mkdir(parents=True, exist_ok=True)
            for r in results:
                if output_format == "markdown":
                    r.save_to_markdown(str(output_path))
                elif output_format == "json":
                    r.save_to_json(str(output_path))
                else:
                    r.save_to_text(str(output_path))
        return

    # stdout
    if output_format == "json":
        payload = [{"page": i + 1, "text": r.clean_text} for i, r in enumerate(results)]
        print(json.dumps(payload if len(payload) > 1 else payload[0],
                         ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            if len(results) > 1:
                print(f"\n--- Page {i+1} ---")
            print(r.clean_text)


def main() -> int:
    args = parse_args()
    validate_input(args.input)

    api_key = _get_api_key()

    # Parse page selection if provided
    pages = None
    if args.pages:
        ext = Path(args.input).suffix.lower()
        if ext != ".pdf":
            print("[ocr_api] --pages is only valid for PDF inputs, ignoring.", file=sys.stderr)
        else:
            # We need the page count; open the PDF briefly
            try:
                import fitz
                doc = fitz.open(args.input)
                total = len(doc)
                doc.close()
                pages = _parse_pages(args.pages, total)
                if not pages:
                    raise SystemExit(f"No valid pages in range '{args.pages}' (PDF has {total} pages).")
            except ImportError:
                print("[ocr_api] PyMuPDF not available, ignoring --pages.", file=sys.stderr)

    max_image_bytes = int(args.max_image_mb * 1024 * 1024)

    results = run_prediction(
        args.input, api_key, args.model, args.base_url,
        timeout=args.timeout, dpi=args.dpi, raw=args.raw,
        max_tokens=args.max_tokens,
        max_image_bytes=max_image_bytes,
        pages=pages,
    )
    out_fmt = args.format
    save_or_print(results, out_fmt, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
