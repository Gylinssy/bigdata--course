from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

SLIDES = [
    {
        'layout': 'cover',
        'title': '基于知识图谱与超图推理的\n创新创业教学智能体',
        'subtitle': '第一次迭代汇报\n从研究方案走向可运行原型',
        'meta_left': ['成员：杨尚昕', '高文宇', '组名：Deepsleep'],
        'meta_right': ['关键词', 'MVP闭环', 'Evidence Trace', 'OCR ingest', 'Streamlit / API / CLI'],
    },
    {
        'title': '第一次迭代的定位',
        'subtitle': '从“研究设计”切到“原型验证”',
        'bullets': [
            '上一版PPT重点回答为什么做、理论如何建模、系统应如何分层。',
            '这一次汇报重点回答第一次迭代究竟落下了什么，以及是否已经跑通闭环。',
            '判断标准不是功能是否完美，而是是否已经具备演示、调试、继续扩展的基础。',
        ],
        'side_title': '本次核心问题',
        'side_lines': ['做了什么', '是否跑通', '离研究目标还差什么'],
    },
    {
        'title': '第一次迭代目标与边界',
        'subtitle': '先打通 happy path，再增强知识图谱与超图推理深度',
        'bullets': [
            '统一使用 DeepSeek OpenAI-compatible 接口作为 LLM 接入层。',
            '学生端必须形成四段式输出：Diagnosis / Evidence / Impact / Next Task。',
            'OCR 作为一等公民接入，保证案例 PDF 后续可被检索引用。',
            '教师端先做简版聚合，不追求复杂可视化，只保证数据能汇总。',
        ],
        'side_title': 'Done Definition',
        'side_lines': ['CLI 可跑', 'API 可调', 'UI 可演示', '最小测试通过'],
    },
    {
        'title': '当前已实现的原型架构',
        'subtitle': '从输入到反馈形成单条可解释流水线',
        'bullets': [
            '项目文本输入 -> ProjectExtractor 抽取结构化字段与 evidence。',
            'RuleEngine 执行 H1 / H4 / H8 / H11，返回带证据的规则结果。',
            'RubricScorer 结合规则与字段完整度输出 R1~R5。',
            'CaseStore 从 OCR 案例库检索证据，ProjectCoachPipeline 汇总并只给一个 Next Task。',
        ],
        'side_title': '技术栈',
        'side_lines': ['Python 3.11', 'FastAPI', 'Streamlit', 'PyMuPDF', '本地向量索引'],
    },
    {
        'title': '已完成的核心模块',
        'subtitle': '一迭代不是概念验证，而是一个可运行的软件骨架',
        'bullets': [
            'DeepSeek 客户端封装：支持标准 chat 调用与 JSON 解析重试。',
            '核心数据模型：ProjectState / EvidenceItem / RuleResult / CoachOutput。',
            'OCR ingest：PDF -> pages.jsonl -> chunks.jsonl -> index。',
            'Demo 入口齐备：CLI、FastAPI、Streamlit 三套入口已经接通。',
        ],
        'side_title': '实际代码落点',
        'side_lines': ['src/core/', 'src/app/', 'src/ui/', 'scripts/', 'tests/'],
    },
    {
        'title': '学生端闭环已经跑通',
        'subtitle': '输入项目描述后，系统会收敛成一个单点瓶颈任务',
        'bullets': [
            '先抽取项目字段，再触发规则，再完成 Rubric 评分。',
            '系统不会给一串散乱建议，而是按 severity/status 排序只保留一个 Next Task。',
            '输出结果带 evidence_used，确保教师和学生都能追溯判断依据。',
            '结果会自动存档为 JSON，便于后续做教师看板和班级聚合。',
        ],
        'side_title': '输出结构',
        'side_lines': ['Current Diagnosis', 'Evidence Used', 'Impact', 'Next Task'],
    },
    {
        'title': 'OCR 与案例证据链',
        'subtitle': '把案例 PDF 纳入诊断链条，是这次原型的重要增量',
        'bullets': [
            'OCR 支持 auto 选择：DeepSeek-OCR -> Tesseract -> pdf_text fallback。',
            '批量 ingest 后会产出 pages.jsonl 与 chunks.jsonl，并建立本地 index。',
            '案例证据可回写为 [case: doc_id p.page_no] "quote" 的格式。',
            '这使系统从只看学生输入，扩展为可以参考案例库的半 RAG 模式。',
        ],
        'side_title': '当前判断',
        'side_lines': ['流程已打通', '接口已预留', '证据格式已统一', '真实案例库仍待补充'],
    },
    {
        'title': '规则与评价的最小可用集',
        'subtitle': '先用 4 条高价值规则验证机制，再扩到全量规则',
        'bullets': [
            '已实现 H1 客户-价值-渠道、H4 TAM/SAM/SOM、H8 单位经济、H11 合规风险。',
            '规则配置使用 YAML + checker，新增规则不需要重写整套框架。',
            'Rubric 评分目前覆盖 R1~R5，优先体现结构诊断与风险准备度。',
            '这一步验证的是“规则可计算、评价可解释、任务可收敛”。',
        ],
        'side_title': '尚未完成',
        'side_lines': ['H1~H15 全量规则', '正式超图求解器', '课程知识图谱挂接'],
    },
    {
        'title': '样例输出：护苗AI',
        'subtitle': '当前系统已经能给出结构化判断，而不是泛泛建议',
        'bullets': [
            '项目主题涉及中学生心理健康筛查，具备明显的敏感数据与合规风险。',
            '系统识别出 H8 fail：LTV/CAC = 2.00，单位经济不足。',
            '系统同时识别 H11 high_risk：涉及学生与心理健康，但未提供合规说明。',
            '最终只保留一个动作：先重算 LTV 与 CAC，并给出明确验收标准。',
        ],
        'side_title': '样例分数',
        'side_lines': ['R1 = 4/5', 'R3 = 4/5', 'R4 = 2/5', 'R5 = 1/5'],
    },
    {
        'title': '教师端与演示前端',
        'subtitle': '第一次迭代已经不是纯后端脚本，而是可演示系统',
        'bullets': [
            '教师看板可读取归档结果，聚合 Top rule、high-risk 项目与字段缺失热区。',
            'Streamlit 前端覆盖三类场景：项目诊断、案例 OCR、教师看板。',
            'FastAPI 暴露 /chat/project_coach、/cases/ingest、/dashboard/teacher。',
            '这让后续教学试点不必从命令行起步，进入门槛已经明显降低。',
        ],
        'side_title': '三种入口',
        'side_lines': ['CLI', 'FastAPI', 'Streamlit'],
    },
    {
        'title': '本轮验证结果',
        'subtitle': '重点不是性能指标，而是系统闭环是否成立',
        'bullets': [
            '最小测试集已通过 5 项，覆盖规则、OCR ingest、pipeline smoke。',
            'CLI happy path 已跑通，能够输出 diagnosis / evidence / next task。',
            '项目归档 JSON 已生成，说明从输入到结果存档路径成立。',
            'Streamlit UI 已接上核心 pipeline，说明前后端集成成本可控。',
        ],
        'side_title': '验证结论',
        'side_lines': ['可运行', '可演示', '可测试', '可继续扩展'],
    },
    {
        'title': '与开题方案的对应关系',
        'subtitle': '一迭代不是完整实现，但每一层都已有最小映射',
        'bullets': [
            '知识图谱层：当前先用 ontology.yaml 和规则字段结构替代完整 KG。',
            '超图规则层：当前以规则引擎近似，优先验证结构约束是否有效。',
            '多 Agent 层：当前以单 pipeline 编排代替，避免早期过度复杂化。',
            '评价与证据链：这一层已经真实落地，是最接近研究目标的部分。',
        ],
        'side_title': '策略判断',
        'side_lines': ['先闭环', '后增强', '先证明价值', '再做复杂推理'],
    },
    {
        'title': '当前不足与差距',
        'subtitle': '系统已具备原型价值，但离研究目标还有明确距离',
        'bullets': [
            '尚未接入真实规模的案例 PDF 库，因此 OCR/RAG 的教学价值还缺少充分样本。',
            'DeepSeek API 的真实在线调用路径已封装，但缺少稳定联网环境下的端到端实测。',
            '所谓“超图推理”当前主要表现为规则校验，还没有形成正式的超图计算框架。',
            '教师端聚合逻辑已存在，但归档样本数过少，尚不足以支撑教学研究结论。',
        ],
        'side_title': '本质问题',
        'side_lines': ['数据不够', '规则不够全', '推理不够深', '试点尚未开始'],
    },
    {
        'title': '第一次迭代的实际收获',
        'subtitle': '最重要的不是“做了多少”，而是明确了系统真正该怎么长出来',
        'bullets': [
            '明确了证据链和单任务反馈，是系统价值感最强的两个输出。',
            '证明了 OCR、规则、Rubric、任务生成可以收束成同一条流水线。',
            '把原本抽象的研究问题转成了代码结构、接口和测试边界。',
            '为后续做 KG、超图、多 Agent 留下了稳定的承载骨架。',
        ],
        'side_title': '从 0 到 1',
        'side_lines': ['可讲清', '可跑通', '可维护', '可扩展'],
    },
    {
        'title': '第二次迭代目标',
        'subtitle': '下一阶段要从“原型成立”进入“能力增强”',
        'bullets': [
            '补齐真实 DeepSeek API / OCR 服务实测，完成在线路径验证。',
            '扩充案例 PDF 数据，真正让检索证据进入学生端反馈。',
            '从 4 条规则扩展到 H1~H15，并引入更明确的超图闭环表达。',
            '把教师看板从 JSON 聚合推进到更适合试点使用的分析界面。',
        ],
        'side_title': '优先级排序',
        'side_lines': ['1. 数据', '2. 推理', '3. 评价', '4. 试点'],
    },
    {
        'title': '建议的二迭代排期',
        'subtitle': '按“先补数据、再补推理、最后进试点”推进',
        'bullets': [
            '第 1 周：接真实案例 PDF、完成 ingest 批处理与索引整理。',
            '第 2 周：补规则集、引入更清晰的超图一致性表达。',
            '第 3 周：接通在线 DeepSeek 调用并修正 prompt / evidence 输出。',
            '第 4 周：准备试点班级演示材料，收集教师反馈与真实样本。',
        ],
        'side_title': '阶段目标',
        'side_lines': ['数据可用', '规则更强', '反馈更稳', '开始试点'],
    },
    {
        'title': '目前最需要的资源',
        'subtitle': '第二次迭代能否起量，取决于数据和试点条件',
        'bullets': [
            '课程案例 PDF、往年项目材料、评分样例，用于建立 OCR 案例库。',
            '教师对 Rubric 的校准意见，用于修正规则优先级和评分逻辑。',
            '可用的 OCR 服务环境或 GPU 资源，用于验证扫描件场景。',
            '真实班级或课程试点场景，用于评估系统是否真正提升教学效率。',
        ],
        'side_title': '资源类型',
        'side_lines': ['教学数据', '教师反馈', '算力环境', '试点场景'],
    },
    {
        'title': '第一次迭代结论',
        'subtitle': '系统已经从研究构想进入“可运行原型”阶段',
        'bullets': [
            '我们已经完成第一次迭代最关键的任务：把研究方案收敛成一个能运行、能解释、能继续长大的 MVP。',
            '当前原型已经具备项目诊断、证据链输出、唯一 Next Task、OCR ingest、教师简版聚合和前端演示能力。',
            '接下来真正需要做的不是重写框架，而是补数据、补推理深度、进入试点验证。',
        ],
        'side_title': '一句话总结',
        'side_lines': ['先把闭环跑通', '再把结构做深'],
    },
]

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}
SLIDE_W = 12192000
SLIDE_H = 6858000

def solid_fill(color: str, alpha: int | None = None) -> str:
    if alpha is None:
        return f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
    return f'<a:solidFill><a:srgbClr val="{color}"><a:alpha val="{alpha}"/></a:srgbClr></a:solidFill>'

def shape_no_text(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, color: str, radius: bool = False) -> str:
    geom = 'roundRect' if radius else 'rect'
    avlst = '<a:avLst><a:gd name="adj" fmla="val 12000"/></a:avLst>' if radius else '<a:avLst/>'
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="{geom}">{avlst}</a:prstGeom>{solid_fill(color)}<a:ln w="12700"><a:noFill/></a:ln></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'
    )

def paragraph(text: str, *, size: int, color: str, bold: bool = False, bullet: bool = False, align: str = 'l') -> str:
    if bullet:
        ppr = (
            '<a:pPr marL="177800" indent="-177800" algn="l">'
            '<a:lnSpc><a:spcPct val="115000"/></a:lnSpc>'
            f'<a:buClr><a:srgbClr val="{color}"/></a:buClr><a:buChar char="•"/>'
            '</a:pPr>'
        )
    else:
        ppr = f'<a:pPr algn="{align}"><a:lnSpc><a:spcPct val="115000"/></a:lnSpc></a:pPr>'
    return (
        f'<a:p>{ppr}<a:r><a:rPr lang="zh-CN" sz="{size}" b="{"1" if bold else "0"}">' \
        f'{solid_fill(color)}<a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface="Microsoft YaHei"/>' \
        f'</a:rPr><a:t>{escape(text)}</a:t></a:r><a:endParaRPr lang="zh-CN" sz="{size}"/></a:p>'
    )

def textbox(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paragraphs: list[str], *, fill: str | None = None, line: str | None = None, radius: bool = False) -> str:
    geom = 'roundRect' if radius else 'rect'
    avlst = '<a:avLst><a:gd name="adj" fmla="val 12000"/></a:avLst>' if radius else '<a:avLst/>'
    fill_xml = solid_fill(fill) if fill else '<a:noFill/>'
    line_xml = solid_fill(line, 30000) if line else '<a:noFill/>'
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{geom}">{avlst}</a:prstGeom>'
        f'{fill_xml}<a:ln w="12700">{line_xml}</a:ln></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" lIns="95250" tIns="95250" rIns="95250" bIns="95250"/><a:lstStyle/>'
        f'{"".join(paragraphs)}</p:txBody></p:sp>'
    )

def wrap_slide(shapes: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sld xmlns:a="{NS["a"]}" xmlns:r="{NS["r"]}" xmlns:p="{NS["p"]}">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f'{"".join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )

def cover_slide_xml(data: dict) -> str:
    shapes = []
    sid = 2
    shapes.append(shape_no_text(sid, 'Background', 0, 0, SLIDE_W, SLIDE_H, 'F4F7FB')); sid += 1
    shapes.append(shape_no_text(sid, 'AccentBar', 0, 0, SLIDE_W, 240000, '0F766E')); sid += 1
    shapes.append(shape_no_text(sid, 'AccentBlock', 762000, 533400, 900000, 1200000, '134E4A', True)); sid += 1
    title_lines = data['title'].split('\n')
    shapes.append(textbox(sid, 'Title', 1850000, 700000, 8800000, 1500000, [paragraph(t, size=2800, color='0F172A', bold=True) for t in title_lines])); sid += 1
    shapes.append(textbox(sid, 'Subtitle', 1850000, 2250000, 6500000, 900000, [paragraph(t, size=1700, color='334155') for t in data['subtitle'].split('\n')])); sid += 1
    shapes.append(textbox(sid, 'MetaLeft', 762000, 3600000, 4200000, 1700000, [paragraph(t, size=1500, color='1F2937', bold=i == 0) for i, t in enumerate(data['meta_left'])], fill='FFFFFF', line='CBD5E1', radius=True)); sid += 1
    shapes.append(textbox(sid, 'MetaRight', 5700000, 3600000, 4950000, 1700000, [paragraph(t, size=1600 if i == 0 else 1500, color='0F172A', bold=i == 0) for i, t in enumerate(data['meta_right'])], fill='ECFEFF', line='99F6E4', radius=True)); sid += 1
    shapes.append(textbox(sid, 'Footer', 762000, 5900000, 10500000, 500000, [paragraph('第一次迭代汇报  |  MVP / OCR / Evidence Trace / Teacher Dashboard', size=1100, color='64748B')]))
    return wrap_slide(shapes)

def content_slide_xml(data: dict, slide_no: int) -> str:
    shapes = []
    sid = 2
    shapes.append(shape_no_text(sid, 'Background', 0, 0, SLIDE_W, SLIDE_H, 'F8FAFC')); sid += 1
    shapes.append(shape_no_text(sid, 'AccentBar', 0, 0, SLIDE_W, 180000, '0F766E')); sid += 1
    shapes.append(textbox(sid, 'Tag', 762000, 330000, 1900000, 350000, [paragraph('FIRST ITERATION', size=1000, color='0F766E', bold=True)])); sid += 1
    shapes.append(textbox(sid, 'Title', 762000, 650000, 8500000, 600000, [paragraph(data['title'], size=2500, color='0F172A', bold=True)])); sid += 1
    shapes.append(textbox(sid, 'Subtitle', 762000, 1220000, 8500000, 450000, [paragraph(data['subtitle'], size=1300, color='475569')])); sid += 1
    shapes.append(textbox(sid, 'Main', 762000, 1850000, 6700000, 3900000, [paragraph(t, size=1600, color='334155', bullet=True) for t in data['bullets']], fill='FFFFFF', line='CBD5E1', radius=True)); sid += 1
    side_paras = [paragraph(data['side_title'], size=1600, color='0F172A', bold=True)] + [paragraph(t, size=1400, color='134E4A') for t in data['side_lines']]
    shapes.append(textbox(sid, 'Side', 7900000, 1850000, 3300000, 3900000, side_paras, fill='ECFEFF', line='99F6E4', radius=True)); sid += 1
    shapes.append(shape_no_text(sid, 'FooterLine', 762000, 6070000, 10500000, 25000, 'CBD5E1')); sid += 1
    shapes.append(textbox(sid, 'Footer', 762000, 6170000, 2500000, 250000, [paragraph('研究主题：创新创业教学智能体第一次迭代', size=1000, color='64748B')])); sid += 1
    shapes.append(textbox(sid, 'Page', 10600000, 6170000, 600000, 250000, [paragraph(f'{slide_no:02d}', size=1000, color='0F766E', bold=True, align='r')]))
    return wrap_slide(shapes)

def build_presentation(template_path: Path, output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        with zipfile.ZipFile(template_path, 'r') as zin:
            zin.extractall(temp_dir)
        for index, slide in enumerate(SLIDES, start=1):
            slide_path = temp_dir / 'ppt' / 'slides' / f'slide{index}.xml'
            xml = cover_slide_xml(slide) if slide.get('layout') == 'cover' else content_slide_xml(slide, index)
            slide_path.write_text(xml, encoding='utf-8')
        core_xml = temp_dir / 'docProps' / 'core.xml'
        if core_xml.exists():
            text = core_xml.read_text(encoding='utf-8')
            text = text.replace('基于知识图谱与超图推理的创新创业教学智能体研究', '基于知识图谱与超图推理的创新创业教学智能体第一次迭代汇报')
            core_xml.write_text(text, encoding='utf-8')
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for path in sorted(temp_dir.rglob('*')):
                if path.is_file():
                    zout.write(path, path.relative_to(temp_dir).as_posix())

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    template = root / '_first_iteration_template.pptx'
    output = root / '第一次迭代汇报_创新创业教学智能体.pptx'
    if not template.exists():
        raise FileNotFoundError(template)
    build_presentation(template, output)
    print(output)

if __name__ == '__main__':
    main()
