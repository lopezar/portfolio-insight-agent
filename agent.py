#!/usr/bin/env python3
"""
Portfolio Insight Agent
Analyzes infrastructure portfolio data and generates executive insights.
Supports mock mode (no API key) and live OpenAI-compatible endpoints.
"""

import json
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def load_portfolio(path: str = "sample_data/portfolio.json") -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def score_and_rank(projects: List[Dict]) -> List[Dict]:
    """Deterministic risk + variance ranking."""
    ranked = []
    for p in projects:
        variance = p["forecast_spend_m"] - p["committed_spend_m"]
        variance_pct = (variance / p["committed_spend_m"]) * 100 if p["committed_spend_m"] else 0
        # Combined score: risk (0-10) weighted + absolute variance impact
        impact_score = p["risk_score"] * 0.7 + min(abs(variance_pct) / 10, 3)
        ranked.append({
            **p,
            "variance_m": round(variance, 1),
            "variance_pct": round(variance_pct, 1),
            "impact_score": round(impact_score, 2)
        })
    return sorted(ranked, key=lambda x: x["impact_score"], reverse=True)


def mock_narrative(ranked: List[Dict], portfolio_name: str) -> Dict[str, Any]:
    """Rule-based narrative for demo / no-API mode."""
    top = ranked[:3]
    high_risk = [p for p in ranked if p["risk_score"] >= 6]
    over_budget = [p for p in ranked if p["variance_m"] > 10]

    summary = (
        f"{portfolio_name} contains {len(ranked)} active projects. "
        f"{len(high_risk)} projects carry elevated risk (score ≥ 6). "
        f"{len(over_budget)} projects are currently forecasting material overruns."
    )

    narrative = (
        f"Leadership attention is recommended on {top[0]['name']} ({top[0]['id']}), "
        f"which combines the highest impact score ({top[0]['impact_score']}) with "
        f"{top[0]['risk_notes'].lower()}. "
        f"{top[1]['name']} is the next priority due to {top[1]['risk_notes'].lower()}. "
        f"On-track projects such as {ranked[-1]['name']} can remain on standard reporting cadence."
    )

    actions = [
        f"Escalate {top[0]['id']} — {top[0]['risk_notes']}",
        f"Review commercial terms on {top[1]['id']} before next milestone",
        f"Confirm utility and entitlement path for {top[2]['id']} if still high-risk"
    ]

    return {
        "executive_summary": summary,
        "narrative": narrative,
        "top_actions": actions,
        "ranked_projects": ranked,
        "mode": "mock"
    }


def live_narrative(ranked: List[Dict], portfolio: Dict, model: str = "gpt-4o-mini") -> Dict[str, Any]:
    if OpenAI is None:
        raise RuntimeError("openai package not installed")

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL")  # optional, for Grok / Azure / local
    )

    prompt = f"""You are an executive reporting assistant for infrastructure program leadership.

Portfolio: {portfolio.get('portfolio')}
As-of date: {portfolio.get('as_of')}

Ranked projects (highest impact first):
{json.dumps(ranked, indent=2)}

Produce:
1. A 2-3 sentence executive summary
2. A short narrative (4-6 sentences) suitable for a leadership update
3. Exactly 3 concrete recommended actions

Be direct, specific, and use project IDs. Do not invent numbers not present in the data.
Return valid JSON with keys: executive_summary, narrative, top_actions (array of strings).
"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"}
    )

    content = json.loads(response.choices[0].message.content)
    content["ranked_projects"] = ranked
    content["mode"] = "live"
    return content


def main():
    parser = argparse.ArgumentParser(description="Portfolio Insight Agent")
    parser.add_argument("--live", action="store_true", help="Use live LLM (requires OPENAI_API_KEY)")
    parser.add_argument("--data", default="sample_data/portfolio.json")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    args = parser.parse_args()

    portfolio = load_portfolio(args.data)
    ranked = score_and_rank(portfolio["projects"])

    if args.live:
        if not os.getenv("OPENAI_API_KEY"):
            print("OPENAI_API_KEY not set. Falling back to mock mode.")
            result = mock_narrative(ranked, portfolio["portfolio"])
        else:
            result = live_narrative(ranked, portfolio, args.model)
    else:
        result = mock_narrative(ranked, portfolio["portfolio"])

    print("\n=== EXECUTIVE SUMMARY ===")
    print(result["executive_summary"])
    print("\n=== NARRATIVE ===")
    print(result["narrative"])
    print("\n=== TOP ACTIONS ===")
    for i, action in enumerate(result["top_actions"], 1):
        print(f"{i}. {action}")
    print("\n=== TOP RISK PROJECTS ===")
    for p in result["ranked_projects"][:3]:
        print(f"{p['id']} | {p['name']} | Impact {p['impact_score']} | Risk {p['risk_score']} | Variance ${p['variance_m']}M")

    # Also write structured output
    out_path = Path("output.json")
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nStructured output written to {out_path}")


if __name__ == "__main__":
    main()
