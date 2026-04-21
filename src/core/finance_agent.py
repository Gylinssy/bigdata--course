from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from .llm_client import DeepSeekClient
from .models import (
    FinanceAnalysisOutput,
    FinanceAnalysisRequest,
    FinanceAnalysisResponse,
    FinanceHealth,
    FinanceMetric,
)
from .runtime_log import RuntimeLogger, new_run_id, preview_text

FINANCE_SYSTEM_PROMPT = (
    "You are the finance-commercialization analysis agent inside an entrepreneurship education system. "
    "Return JSON only. Answer in concise Chinese. "
    "Base every judgment on the provided finance metrics and project context. "
    "Do not inject unrelated jargon. Do not fabricate unavailable inputs."
)


class FinanceNarrativeOrganizerAgent:
    def organize(self, output: FinanceAnalysisOutput) -> str:
        metric_map = {item.key: item for item in output.metrics}
        highlights: list[str] = []
        for key in ("monthly_revenue", "monthly_net_profit", "gross_margin_pct", "ltv_cac_ratio", "runway_months"):
            metric = metric_map.get(key)
            if metric and metric.display != "—":
                highlights.append(f"{metric.name}：{metric.display}")

        strength_lines = "\n".join(f"- {item}" for item in output.strengths[:3]) or "- 暂无明显强信号。"
        risk_lines = "\n".join(f"- {item}" for item in output.risks[:3]) or "- 暂无明显高风险。"
        assumption_lines = "\n".join(f"- {item}" for item in output.assumptions[:3]) or "- 当前输入已足够支持基础测算。"

        sections = [
            f"财务结论：{output.summary}",
            f"商业化判断：{output.commercialization_assessment}",
        ]
        if highlights:
            sections.append("关键指标：\n" + "\n".join(f"- {line}" for line in highlights))
        sections.append(f"最强信号：{output.strongest_signal}")
        sections.append(f"最大风险：{output.biggest_risk}")
        sections.append(f"建议动作：{output.next_action}")
        sections.append(f"继续追问：{output.follow_up_question}")
        sections.append("优势依据：\n" + strength_lines)
        sections.append("风险依据：\n" + risk_lines)
        sections.append("当前口径假设：\n" + assumption_lines)
        return "\n\n".join(sections)


class FinanceAgent:
    def __init__(
        self,
        llm_client: DeepSeekClient | None = None,
        archive_dir: Path | str = Path("outputs/projects"),
        organizer: FinanceNarrativeOrganizerAgent | None = None,
        runtime_logger: RuntimeLogger | None = None,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.archive_dir = Path(archive_dir)
        self.organizer = organizer or FinanceNarrativeOrganizerAgent()
        self.runtime_logger = runtime_logger or RuntimeLogger()

    def analyze(self, request: FinanceAnalysisRequest) -> FinanceAnalysisResponse:
        run_id = new_run_id("finance")
        started_at = perf_counter()
        context = None
        context_project_id = None
        self.runtime_logger.log(
            "finance_agent",
            "request_started",
            run_id=run_id,
            user_id=request.user_id,
            requested_project_id=request.project_id,
            include_project_context=request.include_project_context,
            project_summary_preview=preview_text(request.project_summary),
        )

        if request.include_project_context:
            context, context_project_id = self._load_project_context(request.project_id, request.user_id)
        self.runtime_logger.log(
            "finance_agent",
            "project_context_resolved",
            run_id=run_id,
            context_used=context is not None,
            context_project_id=context_project_id,
        )

        fallback_output = self._build_fallback_output(request, context, context_project_id)
        output = fallback_output
        used_llm = False
        model_name = "finance-agent"

        if self.llm_client.available:
            generated = self._generate_with_llm(
                request=request,
                context=context,
                fallback_output=fallback_output,
                context_project_id=context_project_id,
                run_id=run_id,
            )
            if generated is not None:
                output = generated
                used_llm = True
                model_name = self.llm_client.default_model
                self.runtime_logger.log(
                    "finance_agent",
                    "llm_generation_completed",
                    run_id=run_id,
                    model=model_name,
                    health=output.health.value,
                )

        reply = self.organizer.organize(output)
        self.runtime_logger.log(
            "finance_agent",
            "request_completed",
            run_id=run_id,
            used_llm=used_llm,
            model=model_name,
            context_used=context is not None,
            context_project_id=context_project_id,
            health=output.health.value,
            reply_preview=preview_text(reply),
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return FinanceAnalysisResponse(
            reply=reply,
            structured_output=output,
            model=model_name,
            used_llm=used_llm,
            context_used=context is not None,
            context_project_id=context_project_id,
        )

    def _build_fallback_output(
        self,
        request: FinanceAnalysisRequest,
        context: dict[str, Any] | None,
        context_project_id: str | None,
    ) -> FinanceAnalysisOutput:
        metrics = self._calculate_metrics(request)
        health, summary, commercialization_assessment, strongest_signal, biggest_risk, next_action, follow_up_question, strengths, risks, assumptions = self._diagnose_metrics(
            request=request,
            metrics=metrics,
            context=context,
        )
        return FinanceAnalysisOutput(
            health=health,
            summary=summary,
            commercialization_assessment=commercialization_assessment,
            strongest_signal=strongest_signal,
            biggest_risk=biggest_risk,
            next_action=next_action,
            follow_up_question=follow_up_question,
            strengths=strengths,
            risks=risks,
            assumptions=assumptions,
            metrics=metrics,
            context_project_id=context_project_id,
        )

    def _generate_with_llm(
        self,
        *,
        request: FinanceAnalysisRequest,
        context: dict[str, Any] | None,
        fallback_output: FinanceAnalysisOutput,
        context_project_id: str | None,
        run_id: str | None = None,
    ) -> FinanceAnalysisOutput | None:
        metric_summary = [
            {
                "key": item.key,
                "name": item.name,
                "value": item.value,
                "display": item.display,
                "note": item.note,
            }
            for item in fallback_output.metrics
        ]
        schema = {
            "health": "strong|conditional|risky",
            "summary": "string",
            "commercialization_assessment": "string",
            "strongest_signal": "string",
            "biggest_risk": "string",
            "next_action": "string",
            "follow_up_question": "string",
            "strengths": ["string", "string"],
            "risks": ["string", "string"],
            "assumptions": ["string", "string"],
        }
        user_prompt = (
            "你现在是项目财务管理 Agent 的分析模块。请根据项目描述、项目上下文和已算出的财务指标，"
            "输出一个商业化可行性分析 JSON，不要输出 markdown，不要输出代码块。\n\n"
            "要求：\n"
            "1. 只能围绕给定项目和财务数据分析，不能引入无关创业术语。\n"
            "2. 如果数据不足，必须明确指出缺口，而不是假装已经成立。\n"
            "3. next_action 必须只给一个当前最值得优先做的动作。\n"
            "4. strongest_signal 和 biggest_risk 必须尽量引用真实财务指标，而不是空话。\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"项目输入:\n{request.model_dump_json(indent=2)}\n\n"
            f"项目上下文:\n{json.dumps(context or {}, ensure_ascii=False, indent=2)}\n\n"
            f"已计算指标:\n{json.dumps(metric_summary, ensure_ascii=False, indent=2)}\n\n"
            f"保底结论:\n{fallback_output.model_dump_json(indent=2)}"
        )
        self.runtime_logger.log(
            "finance_agent",
            "llm_generation_started",
            run_id=run_id,
            model=self.llm_client.default_model,
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt=FINANCE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_client.default_model,
                temperature=0.2,
            )
        except Exception as exc:
            self.runtime_logger.log_exception(
                "finance_agent",
                "llm_generation_failed",
                run_id=run_id,
                model=self.llm_client.default_model,
                error=exc,
            )
            return None

        merged = fallback_output.model_dump(mode="json")
        for key in (
            "health",
            "summary",
            "commercialization_assessment",
            "strongest_signal",
            "biggest_risk",
            "next_action",
            "follow_up_question",
            "strengths",
            "risks",
            "assumptions",
        ):
            if key in data and data[key]:
                merged[key] = data[key]
        merged["metrics"] = fallback_output.metrics
        merged["context_project_id"] = context_project_id
        try:
            return FinanceAnalysisOutput.model_validate(merged)
        except Exception:
            return None

    def _calculate_metrics(self, request: FinanceAnalysisRequest) -> list[FinanceMetric]:
        unit_price = self._positive_or_none(request.unit_price)
        unit_variable_cost = self._nonnegative_or_none(request.unit_variable_cost)
        monthly_sales_volume = self._positive_or_none(request.monthly_sales_volume)
        monthly_fixed_cost = self._nonnegative_or_none(request.monthly_fixed_cost) or 0.0
        monthly_marketing_cost = self._nonnegative_or_none(request.monthly_marketing_cost) or 0.0
        monthly_team_cost = self._nonnegative_or_none(request.monthly_team_cost) or 0.0
        monthly_other_cost = self._nonnegative_or_none(request.monthly_other_cost) or 0.0
        cash_on_hand = self._nonnegative_or_none(request.cash_on_hand)
        upfront_investment = self._nonnegative_or_none(request.upfront_investment) or 0.0
        new_customers_per_month = self._positive_or_none(request.new_customers_per_month)
        stated_cac = self._positive_or_none(request.cac)
        avg_orders_per_customer_per_year = self._positive_or_none(request.average_orders_per_customer_per_year)
        customer_lifetime_months = self._positive_or_none(request.customer_lifetime_months)

        fixed_cost_base = monthly_fixed_cost + monthly_marketing_cost + monthly_team_cost + monthly_other_cost
        monthly_revenue = unit_price * monthly_sales_volume if unit_price is not None and monthly_sales_volume is not None else None
        monthly_variable_cost = (
            unit_variable_cost * monthly_sales_volume if unit_variable_cost is not None and monthly_sales_volume is not None else None
        )
        gross_profit = monthly_revenue - monthly_variable_cost if monthly_revenue is not None and monthly_variable_cost is not None else None
        gross_margin_pct = self._ratio_to_percent(gross_profit, monthly_revenue)
        monthly_total_cost = monthly_variable_cost + fixed_cost_base if monthly_variable_cost is not None else None
        monthly_net_profit = monthly_revenue - monthly_total_cost if monthly_revenue is not None and monthly_total_cost is not None else None
        net_margin_pct = self._ratio_to_percent(monthly_net_profit, monthly_revenue)
        contribution_margin_per_unit = (
            unit_price - unit_variable_cost if unit_price is not None and unit_variable_cost is not None else None
        )
        break_even_units = (
            fixed_cost_base / contribution_margin_per_unit
            if contribution_margin_per_unit is not None and contribution_margin_per_unit > 0
            else None
        )
        break_even_revenue = break_even_units * unit_price if break_even_units is not None and unit_price is not None else None
        implied_cac = (
            monthly_marketing_cost / new_customers_per_month
            if monthly_marketing_cost > 0 and new_customers_per_month is not None and new_customers_per_month > 0
            else None
        )
        effective_cac = stated_cac if stated_cac is not None else implied_cac
        customer_lifetime_years = customer_lifetime_months / 12 if customer_lifetime_months is not None else None
        estimated_ltv = (
            contribution_margin_per_unit * avg_orders_per_customer_per_year * customer_lifetime_years
            if contribution_margin_per_unit is not None
            and contribution_margin_per_unit > 0
            and avg_orders_per_customer_per_year is not None
            and customer_lifetime_years is not None
            else None
        )
        ltv_cac_ratio = estimated_ltv / effective_cac if estimated_ltv is not None and effective_cac is not None and effective_cac > 0 else None
        monthly_burn = max(-monthly_net_profit, 0.0) if monthly_net_profit is not None else None
        available_cash = max((cash_on_hand or 0.0) - upfront_investment, 0.0) if cash_on_hand is not None else None
        runway_months = (
            available_cash / monthly_burn
            if available_cash is not None and monthly_burn is not None and monthly_burn > 0
            else None
        )
        monthly_contribution_per_customer = (
            contribution_margin_per_unit * avg_orders_per_customer_per_year / 12
            if contribution_margin_per_unit is not None
            and contribution_margin_per_unit > 0
            and avg_orders_per_customer_per_year is not None
            else None
        )
        payback_months = (
            effective_cac / monthly_contribution_per_customer
            if effective_cac is not None
            and effective_cac > 0
            and monthly_contribution_per_customer is not None
            and monthly_contribution_per_customer > 0
            else None
        )

        metrics = [
            self._metric("monthly_revenue", "月收入", monthly_revenue, "元", "单价 × 月销量"),
            self._metric("monthly_variable_cost", "月变动成本", monthly_variable_cost, "元", "单笔变动成本 × 月销量"),
            self._metric("gross_profit", "毛利润", gross_profit, "元", "月收入 - 月变动成本"),
            self._metric("gross_margin_pct", "毛利率", gross_margin_pct, "%", "毛利润 / 月收入"),
            self._metric("monthly_total_cost", "月总成本", monthly_total_cost, "元", "变动成本 + 固定/团队/营销/其他成本"),
            self._metric("monthly_net_profit", "月净利润", monthly_net_profit, "元", "月收入 - 月总成本"),
            self._metric("net_margin_pct", "净利率", net_margin_pct, "%", "月净利润 / 月收入"),
            self._metric("contribution_margin_per_unit", "单笔贡献毛利", contribution_margin_per_unit, "元", "单价 - 单笔变动成本"),
            self._metric("break_even_units", "盈亏平衡销量", break_even_units, "单/月", "固定成本 ÷ 单笔贡献毛利"),
            self._metric("break_even_revenue", "盈亏平衡收入", break_even_revenue, "元/月", "盈亏平衡销量 × 单价"),
            self._metric("implied_cac", "推导 CAC", implied_cac, "元/人", "营销费用 ÷ 月新增客户"),
            self._metric("effective_cac", "有效 CAC", effective_cac, "元/人", "优先使用手工输入 CAC，否则用推导 CAC"),
            self._metric("estimated_ltv", "估算 LTV", estimated_ltv, "元/人", "单笔贡献毛利 × 年购买频次 × 生命周期"),
            self._metric("ltv_cac_ratio", "LTV/CAC", ltv_cac_ratio, "x", "估算 LTV ÷ 有效 CAC"),
            self._metric("monthly_burn", "月烧钱额", monthly_burn, "元", "净利润为负时的绝对值"),
            self._metric("runway_months", "现金跑道", runway_months, "月", "可用现金 ÷ 月烧钱额"),
            self._metric("payback_months", "获客回本期", payback_months, "月", "有效 CAC ÷ 单客月贡献毛利"),
        ]
        return metrics

    def _diagnose_metrics(
        self,
        *,
        request: FinanceAnalysisRequest,
        metrics: list[FinanceMetric],
        context: dict[str, Any] | None,
    ) -> tuple[
        FinanceHealth,
        str,
        str,
        str,
        str,
        str,
        str,
        list[str],
        list[str],
        list[str],
    ]:
        metric_map = {item.key: item.value for item in metrics}
        strengths: list[str] = []
        risks: list[str] = []
        assumptions: list[str] = []
        score = 0

        gross_margin_pct = metric_map.get("gross_margin_pct")
        monthly_net_profit = metric_map.get("monthly_net_profit")
        contribution_margin_per_unit = metric_map.get("contribution_margin_per_unit")
        break_even_units = metric_map.get("break_even_units")
        monthly_sales_volume = self._positive_or_none(request.monthly_sales_volume)
        ltv_cac_ratio = metric_map.get("ltv_cac_ratio")
        runway_months = metric_map.get("runway_months")
        monthly_revenue = metric_map.get("monthly_revenue")
        effective_cac = metric_map.get("effective_cac")
        estimated_ltv = metric_map.get("estimated_ltv")

        if monthly_revenue is None:
            risks.append("还没有形成完整的价格 × 销量收入口径，商业化判断目前只能停留在假设层。")
            assumptions.append("请补单价和月销量，否则无法判断最基本的收入上限。")

        if contribution_margin_per_unit is None:
            assumptions.append("缺少单价或单笔变动成本，无法判断每做一单到底赚还是亏。")
        elif contribution_margin_per_unit <= 0:
            score -= 2
            risks.append("单笔贡献毛利为负，说明单靠放量无法自然跑通商业模式。")
        else:
            score += 1
            strengths.append("单笔贡献毛利为正，至少具备继续优化单位经济的基础。")

        if gross_margin_pct is None:
            assumptions.append("缺少毛利率口径，当前无法判断收入质量。")
        elif gross_margin_pct >= 60:
            score += 2
            strengths.append(f"毛利率约为 {gross_margin_pct:.1f}%，毛利空间较充足。")
        elif gross_margin_pct >= 35:
            score += 1
            strengths.append(f"毛利率约为 {gross_margin_pct:.1f}%，仍有可优化空间。")
        else:
            score -= 1
            risks.append(f"毛利率约为 {gross_margin_pct:.1f}%，一旦获客或履约成本上升会比较脆弱。")

        if monthly_net_profit is None:
            assumptions.append("缺少净利润测算，无法判断当前商业化节奏是否过快。")
        elif monthly_net_profit > 0:
            score += 2
            strengths.append(f"当前模型下月净利润约为 {monthly_net_profit:.0f} 元，已经接近可自我循环。")
        else:
            score -= 1
            risks.append(f"当前模型下月净利润约为 {monthly_net_profit:.0f} 元，仍处于持续烧钱状态。")

        if break_even_units is not None and monthly_sales_volume is not None:
            if monthly_sales_volume >= break_even_units:
                score += 2
                strengths.append("当前月销量已经覆盖或接近盈亏平衡点。")
            else:
                score -= 1
                risks.append(f"当前月销量低于盈亏平衡点，至少要做到约 {break_even_units:.0f} 单/月才能打平。")
        elif break_even_units is None:
            assumptions.append("贡献毛利不清晰，暂时无法算出盈亏平衡点。")

        if effective_cac is None:
            assumptions.append("缺少 CAC 或新增客户口径，获客效率还不可验证。")
        if estimated_ltv is None:
            assumptions.append("缺少生命周期或复购频次口径，LTV 仍是空白。")

        if ltv_cac_ratio is not None:
            if ltv_cac_ratio >= 3:
                score += 2
                strengths.append(f"LTV/CAC 约为 {ltv_cac_ratio:.2f}，获客回报关系较健康。")
            elif ltv_cac_ratio >= 1.5:
                score += 1
                strengths.append(f"LTV/CAC 约为 {ltv_cac_ratio:.2f}，但还没有形成足够宽的安全边际。")
            else:
                score -= 2
                risks.append(f"LTV/CAC 约为 {ltv_cac_ratio:.2f}，说明当前获客投入很可能回不来。")

        if runway_months is not None:
            if runway_months >= 12:
                score += 1
                strengths.append(f"按当前烧钱速度，现金跑道约 {runway_months:.1f} 个月，短期试错空间尚可。")
            elif runway_months < 6:
                score -= 2
                risks.append(f"现金跑道仅约 {runway_months:.1f} 个月，商业化验证窗口偏短。")
        elif request.cash_on_hand is None:
            assumptions.append("未提供现金储备，暂时无法判断项目还能撑多久。")

        if score >= 4:
            health = FinanceHealth.STRONG
            summary = "从当前测算看，项目已经具备较明确的商业化基础，关键问题是继续验证规模化时这些指标能否保持。"
        elif score >= 1:
            health = FinanceHealth.CONDITIONAL
            summary = "从当前测算看，项目具备一定商业化可能，但关键财务口径仍然偏脆弱，需要先补关键证据再放大。"
        else:
            health = FinanceHealth.RISKY
            summary = "从当前测算看，项目的商业化可行性仍偏弱，优先要修复单位经济或获客回报，而不是继续放大投入。"

        context_hint = ""
        if context and context.get("current_diagnosis"):
            context_hint = f" 当前项目诊断里最相关的提醒是“{context['current_diagnosis']}”。"

        strongest_signal = strengths[0] if strengths else "当前输入还没有出现足够强的财务正信号。"
        biggest_risk = risks[0] if risks else "当前最大的风险不是计算结果，而是口径仍不完整。"

        if contribution_margin_per_unit is not None and contribution_margin_per_unit <= 0:
            next_action = "先重算单笔毛利，把定价、履约成本和服务边界压成一张单位经济表。"
            follow_up_question = "如果你每卖出一单就亏钱，接下来你更可能调价，还是先砍掉高成本交付环节？"
        elif ltv_cac_ratio is not None and ltv_cac_ratio < 3:
            next_action = "先把 CAC、复购频次和生命周期假设拆开验证，不要直接引用一个笼统的 LTV/CAC 结论。"
            follow_up_question = "你现在最不确定的，是 CAC 口径，还是复购/留存口径？"
        elif break_even_units is not None and monthly_sales_volume is not None and monthly_sales_volume < break_even_units:
            next_action = "先围绕一个渠道做最小销量验证，把月销量推到接近盈亏平衡点再决定是否扩投。"
            follow_up_question = "你最有把握先做起来的渠道，单月能稳定带来多少单？"
        else:
            next_action = "把当前财务模型做成乐观、基准、保守三档敏感性表，再决定商业化节奏。"
            follow_up_question = "如果销量、CAC 或复购三项里只能先验证一项，你最想先验证哪一项？"

        commercialization_assessment = (
            f"{summary}{context_hint} 当前最值得看的财务主线是“收入质量 + 获客回报 + 现金跑道”是否能同时成立。"
        )

        return (
            health,
            summary,
            commercialization_assessment,
            strongest_signal,
            biggest_risk,
            next_action,
            follow_up_question,
            strengths[:4],
            risks[:4],
            assumptions[:4],
        )

    def _load_project_context(self, project_id: str | None, user_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
        if not self.archive_dir.exists():
            return None, None

        payload: dict[str, Any] | None = None
        used_project_id: str | None = None
        if project_id:
            archive_file = self.archive_dir / f"{project_id.removesuffix('.json')}.json"
            if archive_file.exists():
                payload = self._read_json(archive_file)
                used_project_id = project_id.removesuffix(".json")

        if payload is None and user_id:
            candidates = sorted(self.archive_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
            for candidate in candidates:
                data = self._read_json(candidate)
                request = data.get("request") if isinstance(data, dict) else None
                if isinstance(request, dict) and request.get("user_id") == user_id:
                    payload = data
                    used_project_id = request.get("project_id") or candidate.stem
                    break

        if not payload:
            return None, None

        state = payload.get("state", {}) if isinstance(payload, dict) else {}
        output = payload.get("output", {}) if isinstance(payload, dict) else {}
        top_rules: list[str] = []
        for rule in output.get("detected_rules", []):
            if isinstance(rule, dict) and rule.get("status") != "pass":
                top_rules.append(f"{rule.get('rule_id')}:{rule.get('status')}")
            if len(top_rules) >= 3:
                break
        context = {
            "project_name": state.get("project_name"),
            "problem": state.get("problem"),
            "customer_segment": state.get("customer_segment"),
            "current_diagnosis": output.get("current_diagnosis"),
            "next_task": output.get("next_task"),
            "top_non_pass_rules": " / ".join(top_rules) if top_rules else "暂无",
        }
        return context, used_project_id

    @staticmethod
    def _metric(key: str, name: str, value: float | None, unit: str, note: str) -> FinanceMetric:
        if value is None:
            display = "—"
        elif unit == "%":
            display = f"{value:.1f}%"
        elif unit == "x":
            display = f"{value:.2f}x"
        elif unit in {"单/月", "月"}:
            display = f"{value:.1f} {unit}"
        elif unit == "元/人":
            display = f"{value:,.0f} 元/人"
        elif unit == "元/月":
            display = f"{value:,.0f} 元/月"
        elif unit == "元":
            display = f"{value:,.0f} 元"
        else:
            display = f"{value:.2f} {unit}".strip()
        return FinanceMetric(key=key, name=name, value=value, display=display, note=note)

    @staticmethod
    def _ratio_to_percent(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        return numerator / denominator * 100

    @staticmethod
    def _positive_or_none(value: float | None) -> float | None:
        if value is None:
            return None
        return float(value) if float(value) > 0 else None

    @staticmethod
    def _nonnegative_or_none(value: float | None) -> float | None:
        if value is None:
            return None
        return float(value) if float(value) >= 0 else None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
