from __future__ import annotations

from .models import ResearchTask


DISCLAIMER = (
    "本报告基于指定时间范围内的市场数据、公开信息与用户提供的材料生成，仅用于信息整理与研究参考，"
    "不构成投资建议、买卖推荐或收益承诺。市场价格可能快速变化，请独立决策。"
)


def compare_results(results: list[dict]) -> dict:
    completed = [result for result in results if result.get("market_metrics")]
    if not completed:
        return {"summary": "没有足够的已完成股票结果进行比较。", "rankings": {}}
    return {
        "summary": f"已完成 {len(completed)} 只股票的统一口径比较。",
        "rankings": {
            "return": [item["company"]["symbol"] for item in sorted(completed, key=lambda x: x["market_metrics"]["period_return_percent"], reverse=True)],
            "volatility": [item["company"]["symbol"] for item in sorted(completed, key=lambda x: x["market_metrics"]["daily_volatility_percent"], reverse=True)],
            "drawdown": [item["company"]["symbol"] for item in sorted(completed, key=lambda x: x["market_metrics"]["max_drawdown_percent"])],
        },
    }


def generate_report(task: ResearchTask, results: list[dict], comparison: dict, documents: list[dict]) -> str:
    lines = [
        "# 股票研究综合报告",
        "",
        f"- 分析范围：{task.time_range.label}（{task.time_range.start_date} 至 {task.time_range.end_date}）",
        f"- 分析公司：{', '.join(company.name + ' (' + company.symbol + ')' for company in task.companies)}",
        "",
        "## 横向比较",
        "",
        comparison.get("summary", ""),
    ]
    rankings = comparison.get("rankings", {})
    if rankings:
        lines.extend(
            [
                f"- 区间收益排名：{' > '.join(rankings.get('return', []))}",
                f"- 波动率从高到低：{' > '.join(rankings.get('volatility', []))}",
                f"- 最大回撤风险从高到低：{' > '.join(rankings.get('drawdown', []))}",
            ]
        )

    for result in results:
        company = result["company"]
        lines.extend(["", f"## {company['name']} ({company['symbol']})", ""])
        if not result.get("market_metrics"):
            lines.append(f"- 研究未完成：{'; '.join(result.get('warnings', []))}")
            continue
        metrics = result["market_metrics"]
        lines.extend(
            [
                f"- 数据来源：{result['source']}（{result['freshness']}）",
                f"- 区间收益率：{metrics['period_return_percent']}%",
                f"- 日波动率：{metrics['daily_volatility_percent']}%",
                f"- 最大回撤：{metrics['max_drawdown_percent']}%",
                f"- 区间最高 / 最低：{metrics['period_high']} / {metrics['period_low']}",
                f"- 上涨 / 下跌交易日：{metrics['up_days']} / {metrics['down_days']}",
                "",
                "### 显著波动",
            ]
        )
        for move in result.get("significant_moves", []):
            lines.append(f"- {move['date']}：{move['change_percent']}%")
        if result.get("events"):
            lines.extend(["", "### 相关公开事件"])
            for event in result["events"]:
                lines.append(f"- [{event.get('title')}]({event.get('url')})")
        for warning in result.get("warnings", []):
            lines.append(f"- 提示：{warning}")

    if documents:
        lines.extend(["", "## 用户上传材料分析"])
        for document in documents:
            lines.append(f"### {document['name']}")
            if document["status"] == "completed":
                for snippet in document["summary"]:
                    lines.append(f"- {snippet}")
            else:
                lines.append(f"- 解析失败：{document.get('error')}")

    lines.extend(["", "## 研究声明", "", DISCLAIMER])
    return "\n".join(lines)
