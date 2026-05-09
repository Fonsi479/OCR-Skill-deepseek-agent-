# ocr-api — 基于硅基流动 PaddleOCR-VL 的 OCR 技能

一个用于 Cowork 的 OCR 技能，调用硅基流动（SiliconFlow）托管的 [PaddleOCR-VL-1.5](https://github.com/PaddlePaddle/PaddleOCR) 模型进行文字识别和文档解析。纯 Python 标准库实现，无需安装 PaddleOCR 本体。

## 功能特性

- **图片 OCR**：支持 PNG、JPG、WEBP、GIF、BMP、TIFF 格式
- **PDF 解析**：通过 PyMuPDF 自动渲染页面为图片后识别（首次使用自动安装）
- **API Key 自动发现**：依次检查环境变量、用户目录、Documents 文件夹、挂载的工作区
- **失败重试**：网络异常时自动重试 3 次，指数退避（2s → 4s → 8s）
- **输出清理**：自动去除 `<|LOC_N|>` 位置标记，规范化空白字符
- **可配置参数**：DPI、图片大小上限、最大 token 数、页面选择

## 获取免费 API Key

本技能依赖硅基流动的 API，需要先注册账号获取密钥。整个过程免费，无需绑卡。

### 第一步：注册硅基流动账号

访问 [硅基流动官网](https://cloud.siliconflow.cn) 注册账号。

### 第二步：创建 API Key

1. 登录后进入 [API Key 管理页面](https://cloud.siliconflow.cn/account/ak)
2. 点击「新建 API Key」
3. 输入名称（如 `ocr-skill`），点击创建
4. 复制生成的密钥（格式为 `sk-` 开头的一串字符）

> 硅基流动对新用户赠送免费额度，PaddleOCR-VL-1.5 模型在免费额度内可直接使用，无需充值。

### 第三步：配置 API Key

选择以下任一方式，技能会自动发现：

**方式一（推荐）：保存到文件**

```bash
echo "你的API密钥" > ~/Documents/.siliconflow_key
```

**方式二：设置环境变量**（重启终端后依然生效）

```bash
echo 'export SILICONFLOW_API_KEY="你的API密钥"' >> ~/.zshrc
source ~/.zshrc
```

**方式三：临时使用**（仅当前终端会话有效）

```bash
export SILICONFLOW_API_KEY="你的API密钥"
```

> API Key 自动发现顺序：环境变量 `SILICONFLOW_API_KEY` → `~/.siliconflow_key` → `~/Documents/.siliconflow_key` → `/tmp/.siliconflow_key` → 挂载的工作区文件夹。任一位置存在即可，无需重复配置。

## 在 Cowork 中使用

配置好 API Key 后，在 Cowork 中直接使用：

```
/ocr-api
```

然后提供图片或 PDF 路径，技能会自动调用 OCR 并返回识别结果。

## 独立脚本使用

你也可以脱离 Cowork 直接使用脚本：

```bash
# 识别单张图片
python3 scripts/ocr_paddleocr_vl.py --input ./scan.jpg

# 识别 PDF，指定 DPI 和输出目录
python3 scripts/ocr_paddleocr_vl.py --input ./document.pdf --output ./ocr-results --dpi 200

# 只处理指定页面
python3 scripts/ocr_paddleocr_vl.py --input ./document.pdf --pages "1,3-5"

# 高 DPI 扫描件需要调大图片限制
python3 scripts/ocr_paddleocr_vl.py --input ./scan.png --max-image-mb 30

# 以 JSON 格式输出
python3 scripts/ocr_paddleocr_vl.py --input ./scan.jpg --format json
```

### 完整参数说明

```
python3 scripts/ocr_paddleocr_vl.py --help
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | （必填） | 输入图片/PDF 路径或 URL |
| `--output` | stdout | 输出文件或目录 |
| `--format` | text | 输出格式：`text`、`json`、`markdown` |
| `--dpi` | 200 | PDF 渲染 DPI |
| `--timeout` | 120 | API 调用超时（秒） |
| `--raw` | false | 跳过输出清理，保留原始 `<LOC_N>` 标记 |
| `--max-tokens` | 8192 | API 返回最大 token 数 |
| `--max-image-mb` | 20 | 图片文件大小上限（MB），超过会拒绝 |
| `--pages` | 全部 | PDF 页面范围，如 `"1,3-5"` 或 `"2"` |

## 文件结构

```
ocr-api-skill/
├── README.md                    # 英文说明
├── README_zh.md                 # 中文说明（本文件）
├── SKILL.md                     # Cowork 技能指令
├── .gitignore
├── scripts/
│   └── ocr_paddleocr_vl.py     # 独立 CLI 脚本
└── references/
    └── api.md                   # PaddleOCR-VL API 参考
```

## 环境要求

- Python 3.9+
- PyMuPDF（首次处理 PDF 时自动安装）
- 硅基流动 API Key（[免费注册获取](https://cloud.siliconflow.cn/account/ak)）

## 使用技巧

1. **扫描件 DPI 建议**：文字为主的文档使用 150-200 DPI 即可；含图表的页面建议 200-300 DPI
2. **遇到图片超限**：用 `--max-image-mb` 调高上限，或适当降低 `--dpi`
3. **大型 PDF**：用 `--pages` 分批处理，避免单次调用超时
4. **表格识别**：PaddleOCR-VL 对简单表格效果较好，密集多列表格建议单独截图
5. **公式识别**：模型会自动将数学公式转为 LaTeX 格式（如 `\(E=mc^2\)`）

## 常见问题

**Q: 提示 API key missing？**
检查密钥是否已保存到 `~/Documents/.siliconflow_key`，或是否设置了环境变量 `SILICONFLOW_API_KEY`。

**Q: 提示 403/401 错误？**
说明 API Key 无效或未开通 PaddleOCR-VL 模型访问权限。请在[硅基流动控制台](https://cloud.siliconflow.cn/account/ak)检查。

**Q: PDF 识别失败？**
首先确认 PyMuPDF 已安装：`pip install --break-system-packages PyMuPDF`。如果 PDF 页数过多，建议用 `--pages` 分批处理。

**Q: 识别结果不理想？**
尝试提高 DPI（`--dpi 300`）、使用 PNG 格式的清晰扫描件、或对图片进行裁剪预处理。

## 许可

MIT

