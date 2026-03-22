# Codex 开发 Prompt 文档（MVP+OCR：案例 PDF → OCR → 证据链 → 超图规则 → Rubric → Next Task）
> **强约束**：本项目必须支持 **大量 PDF 案例的 OCR**，并且 **LLM 调用必须使用 DeepSeek API**。  
> MVP 目标：先跑通可用闭环——**学生输入项目 → 规则诊断 + Rubric 评分（带证据链）→ 只给一个下一步任务**，同时能从 **OCR 案例库检索证据**。

---

## 0. 你是谁（给 Codex 的角色设定）
你是 Codex（代码实现智能体），要在本仓库中实现一个可运行 MVP。  
**最小原型法原则：**
- 先跑通端到端 happy path，再增强。
- MVP 期间避免过度工程化；但数据结构和接口要可扩展。
- 必须交付：可运行 Demo（CLI 或 Web）、最小测试、清晰 README。

---

## 1. MVP 必须做到什么（功能边界）

### 1.1 角色
- **学生端**：输入项目描述 → 得到诊断、评分、唯一下一步任务。
- **教师端（简版）**：聚合多项目结果 → Top 错误模式 + 高风险项目 + 教学干预建议（JSON 输出即可）。

### 1.2 强制输出结构（必须严格遵守）
“项目教练（核心）”输出四块：
1) `Current Diagnosis`  
2) `Evidence Used`（**必须可追溯**）  
3) `Impact`  
4) `Next Task`（**只给一个**，且含验收标准）

Evidence 追溯来源必须支持：
- 用户输入原文 quote（start/end 可选）
- 抽取字段来源 quote
- OCR 案例库的 `doc_id + page_no + quote`

---

## 2. **DeepSeek API（LLM 侧）**：统一接入要求（必须按此实现）

### 2.1 官方兼容性（你必须按 OpenAI 兼容方式接入）
DeepSeek API **兼容 OpenAI API 格式**，推荐 base_url：`https://api.deepseek.com`，也可使用 `https://api.deepseek.com/v1` 以最大兼容 OpenAI SDK。citeturn0search0  
认证方式为 **Bearer API Key**。citeturn0search12

### 2.2 模型选择（MVP 建议）
- `deepseek-chat`：日常对话/抽取/摘要（便宜快）citeturn0search25  
- `deepseek-reasoner`：需要更强推理/批判的步骤（例如 rule explanation / coach 诊断）citeturn0search8turn0search25  
DeepSeek 还支持 “thinking mode” 的开启方式（模型参数或 thinking 参数）。citeturn0search23

### 2.3 重要兼容性注意（避免踩坑）
- **尽量不要依赖 OpenAI Structured Outputs 的 `response_format`**（部分 OpenAI 兼容提供商不支持或行为不同）。MVP 做法：  
  1) 在 prompt 里要求返回 JSON；  
  2) 服务端用 `json.loads()` 解析；  
  3) 解析失败就重试一次（带“只输出 JSON，不要任何多余文本”的修复提示）。

### 2.4 DeepSeek API 调用示例（Python / OpenAI SDK）
> 注意：你要把这些示例写进 README，并在 `src/core/llm_client.py` 封装成统一 client。

```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a strict JSON generator."},
        {"role": "user", "content": "Return JSON with keys: a,b."}
    ],
    temperature=0
)

text = resp.choices[0].message.content
print(text)
```

---

## 3. **OCR（案例 PDF 侧）**：必须支持扫描件

你明确要求 **需要 OCR**，且案例数量很多。MVP 需要把 OCR 作为一等公民：  
**PDF → 每页渲染成图片 → OCR → page-level JSONL → chunk-level JSONL → 向量检索（证据链引用页码）**

### 3.1 OCR 实现路线（MVP 推荐方案：可落地且可扩展）
MVP 采用“双路 OCR”以降低风险：

**路径 A（推荐，质量更高）：DeepSeek-OCR 模型本地服务（OpenAI 兼容）**
- DeepSeek 官方开源 DeepSeek-OCR（及后续版本）citeturn0search24  
- vLLM 提供 DeepSeek-OCR 的在线 serving 示例，并通过 OpenAI 兼容接口调用citeturn0search9  
做法：
1) 你在 README 给出 `vllm serve ...` 的启动方式（可选 GPU）；  
2) 代码里把 OCR 服务当成一个 OpenAI-compatible base_url（例如 `http://localhost:8000/v1`）；  
3) OCR 输入为 page image（base64 或本地文件），输出为该页文本（必要时 JSON 结构：blocks/lines）。

**路径 B（兜底）：pytesseract OCR**
- 当无法部署 vLLM / 没有 GPU / DeepSeek-OCR 不可用时，fallback 到 Tesseract。
- 兜底策略要写进 `src/core/ocr.py`，并在运行时自动选择可用后端。

> MVP 的验收：至少支持“扫描 PDF”能够抽出可检索文本，并能引用 `doc_id/page_no` 做证据链。

### 3.2 OCR Ingest 脚本（必须实现）
新增：
- `scripts/ingest_pdfs.py`：从 `data/cases/*.pdf` 批量 OCR + 切分 + 入库（向量）

输入：
- `data/cases/*.pdf`
- `data/cases/manifest.csv`（可选：doc_id,title,year,domain,tags）

输出（必须）：
- `outputs/cases/pages.jsonl`（每行=一页）
  - doc_id, page_no, text, ocr_backend, image_hash
- `outputs/cases/chunks.jsonl`（每行=一个 chunk）
  - chunk_id, doc_id, page_no, text, start_char, end_char

向量库（任选其一即可）：
- FAISS（推荐，简单）/ Chroma

### 3.3 证据链引用格式（必须）
EvidenceItem 扩展字段：
- `doc_id: str | None`
- `page_no: int | None`
- `chunk_id: str | None`

当使用案例证据时，必须能够在输出里看到类似：
- `[case: <doc_id> p.<page_no>] "<quote>"`

---

## 4. Repo 结构（请按此创建项目骨架）
```
startup-edu-agent/
  README.md
  pyproject.toml  (or requirements.txt)
  .env.example
  data/
    ontology.yaml
    rubric.yaml
    hyper_rules/
      H1.yaml
      H4.yaml
      H8.yaml
      H11.yaml
    cases/
      manifest.csv            # optional
      *.pdf                   # 大量案例 PDF
    examples/
      project_inputs.jsonl
  outputs/
    cases/                    # OCR 产物 & chunk
  src/
    app/
      main.py                 # FastAPI
      api.py
    core/
      models.py               # Pydantic
      llm_client.py           # DeepSeek API client wrapper（强制）
      extractor.py
      rule_engine.py
      rubric.py
      evidence.py
      ocr/
        backends.py           # deepseek_ocr(vllm) + tesseract
        ingest.py             # pdf->images->ocr->jsonl
      retrieval/
        vector_store.py       # faiss/chroma
        case_store.py         # retrieve_cases(query)->evidence
      prompts/
        system.md
        extractor.md
        critic.md
        coach.md
        reporter.md
      pipeline.py
    tests/
      test_rules.py
      test_ocr_ingest_smoke.py
      test_pipeline_smoke.py
  scripts/
    demo_cli.py
    ingest_pdfs.py
```

---

## 5. 数据结构（Pydantic Models 必须实现）

### 5.1 ProjectState（结构化项目表示，最少字段）
- project_name: str | None
- problem: str | None
- customer_segment: str | None
- value_proposition: str | None
- channel: str | None
- revenue_model: str | None
- cost_structure: str | None
- traction: str | None
- tam: float | None
- sam: float | None
- som: float | None
- ltv: float | None
- cac: float | None
- compliance_notes: str | None

### 5.2 EvidenceItem（证据链，必须可引用 PDF 页码）
- source: "user_input" | "extracted_field" | "rule_result" | "case_pdf"
- quote: str
- start: int | None
- end: int | None
- field: str | None
- doc_id: str | None
- page_no: int | None
- chunk_id: str | None

### 5.3 RuleResult（规则输出）
- rule_id: str
- status: "pass" | "warning" | "fail" | "high_risk"
- severity: "low" | "medium" | "high"
- message: str
- probing_question: str | None
- fix_task: str | None
- evidence: list[EvidenceItem]

### 5.4 CoachOutput（最终给学生）
- current_diagnosis: str
- evidence_used: list[EvidenceItem]
- impact: str
- next_task: str
- rubric_scores: list[RubricScore]
- detected_rules: list[RuleResult]

---

## 6. 超图规则（MVP：4 条必须落地）

必须实现以下四条规则（Python 逻辑 + YAML 配置）：
- H1 客户–价值主张错位（customer/value/channel）
- H4 TAM>=SAM>=SOM
- H8 单位经济（LTV>=3*CAC）
- H11 合规/伦理缺口（医疗/金融/未成年人/隐私等敏感关键词且缺少合规说明 → high_risk）

规则 YAML 至少包含：
- rule_id
- required_fields
- severity
- trigger_message
- probing_question
- fix_task

---

## 7. Pipeline（最小可运行流程）

### 7.1 主流程（学生端）
1) Extractor：用户输入 → ProjectState + evidence（字段 quote）
2) RuleCritic：ProjectState → H1/H4/H8/H11 → RuleResult[]
3) RubricScorer：规则 + 字段完整度 → R1..R5 得分（含 evidence）
4) CaseRetriever（可选但推荐）：用“诊断/问题”作为 query，从 OCR 案例库检索 3 条证据
5) ProjectCoach：汇总 → 只挑一个最关键瓶颈 → Next Task（含验收标准）
6) Reporter：输出 Markdown（学生版）+ JSON（存档）

### 7.2 教师端聚合（简版）
- 从存档 JSON 聚合：Top 规则触发、high_risk 项目、字段缺失热区、建议干预。

### 7.3 “只给一个任务”的策略（必须实现）
- 对 detected_rules 排序：severity(high>medium>low) + status(fail>high_risk>warning>pass)
- 取 top1 作为唯一瓶颈
- Next Task = 该规则 fix_task（若为空则模板生成，但仍只输出一个）

---

## 8. API 设计（FastAPI）

### 8.1 POST /chat/project_coach
```json
{ "user_id": "u1", "project_text": "......", "project_id": "p1(optional)" }
```
返回 CoachOutput JSON。

### 8.2 POST /cases/ingest
触发批量 OCR ingest（MVP 可以只在本地脚本实现；若实现 API 则返回任务状态）。

### 8.3 GET /dashboard/teacher?class_id=xxx
返回聚合统计 JSON。

---

## 9. Demo 要求（必须可跑）
- `scripts/ingest_pdfs.py`：对 `data/cases/*.pdf` OCR + chunk + 向量入库
- `scripts/demo_cli.py`：对 examples 输入跑完整 pipeline，并展示：
  - Current Diagnosis
  - Next Task
  - Triggered Rules
  - Rubric scores
  - Retrieved case evidence（含 doc_id/page_no）

---

## 10. 测试要求（最小但必须有）
- `test_rules.py`：覆盖 H4/H8/H11
- `test_ocr_ingest_smoke.py`：给 1 个扫描 PDF（或渲染图片页）能产出 pages.jsonl/chunks.jsonl
- `test_pipeline_smoke.py`：pipeline 返回 CoachOutput，且 next_task 非空、evidence_used 非空

---

## 11. 环境变量（.env.example 必须提供）
```
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# OCR (vLLM DeepSeek-OCR serving), optional:
DEEPSEEK_OCR_BASE_URL=http://localhost:8000/v1
DEEPSEEK_OCR_MODEL=deepseek-ai/DeepSeek-OCR  # or your served model id

# Vector store config
VECTOR_STORE=faiss
CASE_INDEX_DIR=outputs/cases/index
```

---

## 12. MVP Done 的验收标准
- ✅ OCR：扫描 PDF 可被 ingest，产出 pages/chunks 文件
- ✅ RAG：检索返回带 `doc_id/page_no/quote` 的 evidence
- ✅ DeepSeek API：LLM 调用通过 DeepSeek base_url 跑通（chat & reasoner 可切换）citeturn0search0turn0search8turn0search12
- ✅ 可解释：诊断/评分/任务均有 evidence
- ✅ 可执行：每次只给一个 Next Task（含验收标准）
- ✅ 可扩展：新增规则只需加 YAML + 1 个 checker

---

## 13. Codex 行动清单（按顺序执行）
1) 建 repo 骨架 + 依赖 + README + .env.example  
2) 写 `llm_client.py`（DeepSeek OpenAI-compatible wrapper）  
3) 写 OCR ingest：pdf→images→(DeepSeek-OCR/vLLM 或 tesseract)→pages.jsonl→chunks.jsonl→vector index  
4) 写 extractor（LLM+规则混合，保留 evidence）  
5) 写 rule_engine（H1/H4/H8/H11）  
6) 写 rubric（R1..R5）  
7) 写 coach（只给一个 Next Task）  
8) FastAPI endpoints + demo_cli  
9) Tests + CI（可选）  
10) README：一键运行流程（含 OCR 服务启动说明）  

---

## 附：OCR 服务启动建议（写进 README）
- vLLM serving DeepSeek-OCR（示例见 vLLM recipes）citeturn0search9  
- DeepSeek-OCR 模型来源与版本信息见官方 GitHub release citeturn0search24

> MVP 不要求你把 OCR 做到完美排版；优先保证“可检索 + 可引用页码 + 可追溯证据链”。
