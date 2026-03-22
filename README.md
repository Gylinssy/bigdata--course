# startup-edu-agent

面向创业教育场景的最小原型：`学生项目文本 -> 结构化抽取 -> 超图规则诊断 -> Rubric 评分 -> 只给一个 Next Task`，并支持 `PDF -> OCR -> chunk -> 检索证据链`。

## 已实现

- DeepSeek OpenAI-compatible 客户端封装：`src/core/llm_client.py`
- 项目抽取、4 条规则、Rubric 评分、唯一下一步任务：`src/core/`
- OCR ingest：`scripts/ingest_pdfs.py`
- 本地案例检索与页码证据引用：`src/core/retrieval/`
- CLI Demo：`scripts/demo_cli.py`
- FastAPI：`src/app/main.py`
- 最小测试：`tests/`

## 目录

```text
data/
  hyper_rules/
  examples/
  cases/
outputs/
src/
  app/
  core/
scripts/
tests/
```

## 环境

这台机器默认 `python` 指向 3.6，运行时请显式使用 `py -3.11`。

```powershell
py -3.11 -m pip install -e .[test,ocr]
Copy-Item .env.example .env
```

## DeepSeek 配置

`.env` 至少需要：

```env
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_CHAT_MODEL=deepseek-chat
DEEPSEEK_REASONER_MODEL=deepseek-reasoner
DEEPSEEK_OCR_BASE_URL=http://localhost:8000/v1
DEEPSEEK_OCR_MODEL=deepseek-ai/DeepSeek-OCR
VECTOR_STORE=faiss
CASE_INDEX_DIR=outputs/cases/index
```

## 一键启动

Windows 下可直接双击 [start.bat](/F:/超图与智能体/start.bat) 或在 PowerShell 里执行：

```powershell
.\start.ps1
```

脚本会依次完成：

- 可选安装 `.[test,ocr,ui]` 依赖
- 交互式填写 API Key / Base URL
- 选择普通对话模型和推理模型
- 生成或更新项目根目录下的 `.env`
- 一键启动 CLI、Streamlit 或 FastAPI

Python 调用方式与 OpenAI SDK 兼容：

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
)

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a strict JSON generator."},
        {"role": "user", "content": "Return JSON with keys: a,b."},
    ],
    temperature=0,
)
print(resp.choices[0].message.content)
```

说明：

- 当前 MVP 默认优先走 DeepSeek，若未配置 API Key，会退回到本地启发式抽取，便于离线测试。
- OCR 优先走 DeepSeek-OCR，其次 Tesseract，再其次 `pdf_text` 兜底。

## 运行 Demo

```powershell
py -3.11 scripts/demo_cli.py
```

会输出：

- Current Diagnosis
- Evidence Used
- Impact
- Next Task
- Triggered Rules
- Rubric Scores

## 运行 Streamlit 前端

先安装 UI 依赖：

```powershell
py -3.11 -m pip install -e .[test,ocr,ui]
```

然后启动：

```powershell
py -3.11 -m streamlit run src/ui/streamlit_app.py
```

前端包含四个页面：

- 项目诊断：输入项目文本，直接调用 `ProjectCoachPipeline`
- 对话 Agent：多轮问答，支持 `general/reasoning` 两种模式
- 案例 OCR：上传 PDF，执行 ingest 并生成 `pages/chunks/index`
- 教师看板：读取 `outputs/projects/*.json` 做聚合展示

## 批量 OCR Ingest

将案例 PDF 放到 `data/cases/` 后执行：

```powershell
py -3.11 scripts/ingest_pdfs.py --input-dir data/cases --output-dir outputs/cases --backend auto
```

输出文件：

- `outputs/cases/pages.jsonl`
- `outputs/cases/chunks.jsonl`
- `outputs/cases/index/records.json`

证据引用格式：

```text
[case: <doc_id> p.<page_no>] "<quote>"
```

## 启动 API

```powershell
py -3.11 -m uvicorn app.main:app --app-dir src --reload
```

接口：

- `POST /chat/project_coach`
- `POST /chat/conversation`
- `POST /cases/ingest`
- `GET /dashboard/teacher?class_id=xxx`

`/chat/conversation` 支持项目上下文模式，请求体可加：

```json
{
  "user_id": "u1",
  "mode": "reasoning",
  "include_project_context": true,
  "project_id": "p1",
  "messages": [
    {"role": "user", "content": "结合我当前项目，下一步先做什么？"}
  ]
}
```

API 配置位置：

- 环境变量定义：`.env`（参考 `.env.example`）
- DeepSeek 客户端读取逻辑：`src/core/llm_client.py`
- FastAPI 路由：`src/app/api.py`

示例：

```json
{
  "user_id": "u1",
  "project_id": "p1",
  "project_text": "项目名称：护苗AI\n问题：为中学生提供心理健康筛查和干预建议。\n客户：学校老师和家长。\n价值主张：用问卷和随访提早发现高风险学生。\n渠道：抖音投流获客。\n市场规模：TAM 10000 SAM 5000 SOM 1000\n单位经济：LTV 500 CAC 300"
}
```

## OCR 服务建议

如果你有 GPU 并准备部署 DeepSeek-OCR，可将其作为 OpenAI-compatible 服务暴露到 `DEEPSEEK_OCR_BASE_URL`。当前仓库里的 `DeepSeekOCRBackend` 已按这个接口调用。

如果没有 GPU，可安装 Tesseract 并走：

```powershell
py -3.11 -m pip install pytesseract pillow
```

若两者都不可用，`pdf_text` 仅适用于可直接抽取文本的数字 PDF，不适合纯扫描件。

## 测试

```powershell
py -3.11 -m pytest
```

当前已通过：

- `test_rules.py`
- `test_ocr_ingest_smoke.py`
- `test_pipeline_smoke.py`
