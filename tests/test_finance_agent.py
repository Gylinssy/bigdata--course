from core.finance_agent import FinanceAgent
from core.models import FinanceAnalysisRequest, FinanceHealth


class DummyOfflineClient:
    available = False
    default_model = "deepseek-chat"


class DummyOnlineClient:
    available = True
    default_model = "deepseek-chat"
    last_user_prompt = ""

    def chat_json(self, *, system_prompt: str, user_prompt: str, model: str, temperature: float):  # noqa: ARG002
        self.last_user_prompt = user_prompt
        return {
            "health": "conditional",
            "summary": "模型口径基本完整，但商业化还要继续验证。",
            "commercialization_assessment": "目前已经有正向毛利，但真正的规模化还依赖获客效率和复购稳定性。",
            "strongest_signal": "单笔贡献毛利为正，且月度净利润已经转正。",
            "biggest_risk": "如果 CAC 回升或复购下降，当前结论会迅速变弱。",
            "next_action": "先拿一个真实渠道做 2 周 CAC 与复购联合验证。",
            "follow_up_question": "你现在最想先验证 CAC，还是验证复购？",
            "strengths": ["毛利率较高。", "净利润转正。"],
            "risks": ["CAC 还缺稳定样本。"],
            "assumptions": ["销量口径仍需持续观察。"],
        }


def test_finance_agent_computes_core_metrics_and_health():
    agent = FinanceAgent(llm_client=DummyOfflineClient())
    response = agent.analyze(
        FinanceAnalysisRequest(
            project_summary="校园工具类 SaaS，按订阅收费。",
            unit_price=199,
            unit_variable_cost=69,
            monthly_sales_volume=300,
            monthly_fixed_cost=8000,
            monthly_marketing_cost=3000,
            monthly_team_cost=12000,
            monthly_other_cost=2000,
            cash_on_hand=180000,
            upfront_investment=20000,
            new_customers_per_month=120,
            average_orders_per_customer_per_year=6,
            customer_lifetime_months=18,
        )
    )

    metric_map = {item.key: item for item in response.structured_output.metrics}

    assert response.used_llm is False
    assert response.structured_output.health == FinanceHealth.STRONG
    assert round(metric_map["monthly_revenue"].value or 0, 2) == 59700
    assert round(metric_map["monthly_net_profit"].value or 0, 2) == 14000
    assert round(metric_map["gross_margin_pct"].value or 0, 2) == round((39000 / 59700) * 100, 2)
    assert round(metric_map["break_even_units"].value or 0, 2) == round(25000 / 130, 2)
    assert round(metric_map["ltv_cac_ratio"].value or 0, 2) == round((130 * 6 * 1.5) / 25, 2)
    assert "财务结论" in response.reply


def test_finance_agent_uses_llm_to_override_narrative_but_keeps_metrics():
    llm = DummyOnlineClient()
    agent = FinanceAgent(llm_client=llm)
    response = agent.analyze(
        FinanceAnalysisRequest(
            project_summary="一个面向校内商家的轻量 SaaS。",
            unit_price=99,
            unit_variable_cost=29,
            monthly_sales_volume=180,
            monthly_fixed_cost=6000,
            monthly_marketing_cost=2400,
            monthly_team_cost=8000,
            monthly_other_cost=1600,
            new_customers_per_month=80,
            average_orders_per_customer_per_year=4,
            customer_lifetime_months=12,
        )
    )

    assert response.used_llm is True
    assert response.model == "deepseek-chat"
    assert response.structured_output.health == FinanceHealth.CONDITIONAL
    assert response.structured_output.next_action == "先拿一个真实渠道做 2 周 CAC 与复购联合验证。"
    assert any(item.key == "monthly_revenue" and item.value is not None for item in response.structured_output.metrics)
    assert "已计算指标" in llm.last_user_prompt
