# SiliconFlow PaddleOCR-VL API Reference

## Hosted VLM Backend

Create `PaddleOCRVL` with the VLM recognition backend set to `vllm-server` and point it at SiliconFlow's OpenAI-compatible `/v1` endpoint:

```python
import os
from paddleocr import PaddleOCRVL

pipeline = PaddleOCRVL(
    vl_rec_backend="vllm-server",
    vl_rec_server_url="https://api.siliconflow.cn/v1",
    vl_rec_api_model_name="PaddlePaddle/PaddleOCR-VL-1.5",
    vl_rec_api_key=os.environ["SILICONFLOW_API_KEY"],
)
```

If the platform account uses an unversioned alias, override the model name:

```python
pipeline = PaddleOCRVL(
    vl_rec_backend="vllm-server",
    vl_rec_server_url="https://api.siliconflow.cn/v1",
    vl_rec_api_model_name="PaddlePaddle/PaddleOCR-VL",
    vl_rec_api_key=os.environ["SILICONFLOW_API_KEY"],
)
```

## Prediction Pattern

For images:

```python
output = pipeline.predict(input="./image.png")
for res in output:
    res.save_to_markdown(save_path="./ocr-output")
    res.save_to_json(save_path="./ocr-output")
```

For PDFs:

```python
pages = list(pipeline.predict(input="./document.pdf"))
output = pipeline.restructure_pages(pages)
for res in output:
    res.save_to_markdown(save_path="./ocr-output")
    res.save_to_json(save_path="./ocr-output")
```

Use `restructure_pages(..., merge_tables=True, relevel_titles=True, concatenate_pages=True)` only when the downstream task needs cross-page table merging, heading reconstruction, or a combined document.

## Operational Rules

- Read the API key from `SILICONFLOW_API_KEY`.
- Do not commit or print real API keys.
- Keep `vl_rec_backend="vllm-server"` for SiliconFlow.
- Keep `vl_rec_server_url="https://api.siliconflow.cn/v1"` unless the user provides another compatible endpoint.
- Let callers override the model name because SiliconFlow may expose versioned and unversioned aliases.
