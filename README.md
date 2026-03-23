# startup-edu-agent

面向创业教学场景的 Streamlit + FastAPI 原型系统，当前已重构为更接近 ChatGPT 网页端的左侧导航 + 中间工作区布局，并加入 student / teacher / admin 三类 mock 登录与路由守卫。

## 页面结构

- 学生端
  - 项目诊断（A2/A3/A4）
  - 学习辅导与反代写护栏（A1）
  - 路演评分与动态 Rubric（A5）
  - 多会话追问区
- 教师端
  - 班级看板
  - 评分可视化
  - 风险项目与干预建议
  - 单项目证据溯源
- 功能中心
  - 超图约束可视化
  - 案例 OCR / Ingest
  - 环境状态与部署配置说明
- 管理端
  - 账号与角色管理
  - 全局风险监控
  - 越权拦截状态检查

## 当前技术结构

### 核心逻辑

- 项目诊断：`src/core/pipeline.py`
- 对话代理：`src/core/chat_agent.py`
- 规则引擎：`src/core/rule_engine.py`
- OCR 管线：`src/core/ocr/`

### UI 层

- Streamlit 入口：`src/ui/streamlit_app.py`
- 登录与角色守卫：`src/ui/auth.py`
- 教师端评分数据整理：`src/ui/dashboard_data.py`
- 可视化组件：`src/ui/visuals.py`
- 全局样式：`src/ui/styles.py`

## Mock 登录账号

- 学生端
  - 用户名：`student`
  - 密码：`student123`
- 教师端
  - 用户名：`teacher`
  - 密码：`teacher123`
- 管理端
  - 用户名：`admin`
  - 密码：`admin123`

后续如果接入真实鉴权，优先替换 `src/ui/auth.py` 中的 mock 认证逻辑即可。

## 安装依赖

建议在 Windows 下显式使用 Python 3.11：

```powershell
py -3.11 -m pip install -e .[test,ocr,ui]
Copy-Item .env.example .env
```

## 环境变量

`.env` 至少建议包含：

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

## 运行 Streamlit

```powershell
py -3.11 -m streamlit run src/ui/streamlit_app.py
```

## 运行 API

```powershell
py -3.11 -m uvicorn app.main:app --app-dir src --reload
```

## 测试

```powershell
py -3.11 -m pytest
```

## 资产规模预检（2.2）

在功能中心新增了“资产预检”页，会自动检查以下硬性下限：

- Rubric 维度数量（>=10）
- 赛事模板数量（>=4）
- KG 节点数量（>=100）
- 结构化案例数量（>=50）
- 超边数量（>=20）
- 规则诊断池数量（>=20）
- 追问策略池数量（>=15）

当前结构化案例来源文件：`data/case_library/structured_cases.jsonl`。

## 案例库补全工具

新增脚本：`scripts/case_library_manager.py`

```powershell
# 1) 生成批量录入模板
py -3.11 scripts/case_library_manager.py template --output data/case_library/new_cases_template.jsonl --count 20

# 2) 校验新案例（字段完整性与格式）
py -3.11 scripts/case_library_manager.py validate --input data/case_library/new_cases_template.jsonl --verbose

# 3) 合并进主案例库（自动去重 case_id）
py -3.11 scripts/case_library_manager.py append --input data/case_library/new_cases_template.jsonl --target data/case_library/structured_cases.jsonl

# 4) 导出结构化检索 chunk
py -3.11 scripts/case_library_manager.py export-chunks --input data/case_library/structured_cases.jsonl --output outputs/cases/structured_chunks.jsonl

# 5) 查看案例库统计
py -3.11 scripts/case_library_manager.py stats --input data/case_library/structured_cases.jsonl
```

## 说明

- 学生端已经承接原“输入文本并给出初步诊断结果”的主交互。
- 功能中心不再承担学生主入口，只保留规则、约束、OCR 和配置功能。
- 教师端在无真实项目归档时，会使用内置 mock 数据占位，便于先开发和部署界面。
