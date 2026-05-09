# ocr-api — SiliconFlow PaddleOCR-VL OCR Skill

A Cowork skill that uses SiliconFlow's hosted [PaddleOCR-VL](https://github.com/PaddlePaddle/PaddleOCR) model for OCR and document parsing. Zero heavy dependencies — pure Python stdlib HTTP calls.

## Features

- **Images**: PNG, JPG, WEBP, GIF, BMP, TIFF — all via base64 inline to the API
- **PDFs**: Automatic page rendering via PyMuPDF (auto-installed on first use)
- **API Key Auto-Discovery**: Checks env var, home dir, Documents, mounted workspace folders
- **Retry with backoff**: 3 retries with exponential backoff on transient failures
- **Clean output**: Automatically strips `<|LOC_N|>` position markers
- **Configurable limits**: DPI, image size cap, max tokens, page selection

## Quick Start

1. Get a free API key from [SiliconFlow](https://cloud.siliconflow.cn/account/ak)

2. Save your key (script auto-discovers it):
   ```bash
   echo "your-api-key" > ~/Documents/.siliconflow_key
   ```

3. Install the skill in Cowork, then use:
   ```
   /ocr-api
   ```

## Standalone Script

You can also use the script directly without Cowork:

```bash
# Basic OCR on an image
python3 scripts/ocr_paddleocr_vl.py --input ./scan.jpg

# OCR a PDF with custom DPI and output directory
python3 scripts/ocr_paddleocr_vl.py --input ./document.pdf --output ./ocr-results --dpi 200

# Select specific pages only
python3 scripts/ocr_paddleocr_vl.py --input ./document.pdf --pages "1,3-5"

# High-DPI scans need a larger image limit
python3 scripts/ocr_paddleocr_vl.py --input ./scan.png --max-image-mb 30
```

### Full Options

```
python3 scripts/ocr_paddleocr_vl.py --help
```

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | (required) | Image/PDF path or URL |
| `--output` | stdout | Output file or directory |
| `--format` | text | `text`, `json`, or `markdown` |
| `--dpi` | 200 | DPI for PDF rendering |
| `--timeout` | 120 | API timeout in seconds |
| `--raw` | false | Skip post-processing cleanup |
| `--max-tokens` | 8192 | Max API response tokens |
| `--max-image-mb` | 20 | Max image file size in MB |
| `--pages` | all | Page range (e.g. `"1,3-5"`) for PDFs |

## API Key Discovery Order

1. `SILICONFLOW_API_KEY` environment variable
2. `~/.siliconflow_key`
3. `~/Documents/.siliconflow_key`
4. `/tmp/.siliconflow_key`
5. Mounted workspace folders (VM sandbox auto-detection)

## Supported Formats

- Images: PNG, JPG/JPEG, WEBP, GIF, BMP, TIFF
- Documents: PDF (requires PyMuPDF, auto-installed)

## File Structure

```
ocr-api-skill/
├── SKILL.md              # Cowork skill instructions
├── scripts/
│   └── ocr_paddleocr_vl.py   # Standalone CLI script
└── references/
    └── api.md                # PaddleOCR-VL API reference
```

## Requirements

- Python 3.9+
- `PyMuPDF` (auto-installed on first PDF use)
- A [SiliconFlow](https://cloud.siliconflow.cn) API key with PaddleOCR-VL access

## License

MIT
