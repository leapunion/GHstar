"""Normalization + enrichment: classification, subcategory/module/scenario/risk inference, rubric + trend scoring, and normalize_repo (raw API dict -> Repo)."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from ghstar.model import *  # noqa: F401,F403

def words(repo: dict[str, Any]) -> str:
    bits = [
        repo.get("name") or "",
        repo.get("full_name") or "",
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
        repo.get("language") or "",
    ]
    return " ".join(bits).lower()


def repo_owner(repo: dict[str, Any]) -> str:
    owner = repo.get("owner")
    if isinstance(owner, dict):
        return owner.get("login") or ""
    return str(owner or "")


def repo_url(repo: dict[str, Any]) -> str:
    return repo.get("html_url") or repo.get("url") or ""


def repo_stars(repo: dict[str, Any]) -> int:
    return int(repo.get("stargazers_count") or repo.get("stars") or 0)


def repo_forks(repo: dict[str, Any]) -> int:
    return int(repo.get("forks_count") or repo.get("forks") or 0)


def parse_github_date(value: str, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return fallback


def classify(repo: dict[str, Any], report_date: date | None = None) -> tuple[str, int]:
    as_of = report_date or date.today()
    text = words(repo)
    scores: dict[str, int] = {}
    for category, keywords in FOCUS_AREAS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        scores[category] = score
    category = max(scores, key=scores.get)
    base = scores[category]
    topic_bonus = min(len(repo.get("topics") or []), 6)
    star_bonus = min(repo_stars(repo) // 100, 10)
    freshness_bonus = 3 if repo.get("pushed_at", "")[:10] >= (as_of - timedelta(days=7)).isoformat() else 0
    return category, base * 10 + topic_bonus + star_bonus + freshness_bonus


def infer_subcategory(repo: dict[str, Any], category: str) -> str:
    text = words(repo)
    patterns = [
        ("Commerce Agent", ["commerce", "ecommerce", "shopping", "checkout", "merchant", "retail"]),
        ("Product Intelligence", ["product search", "recommendation", "catalog", "inventory", "pricing"]),
        ("Enterprise Workflow", ["workflow", "orchestration", "handoff", "automation"]),
        ("Knowledge / RAG", ["rag", "knowledge", "retrieval", "document", "vector", "embedding"]),
        ("Evaluation / Observability", ["evaluation", "eval", "benchmark", "observability", "telemetry"]),
        ("Agent Runtime", ["agent runtime", "multi-agent", "tool calling", "autonomous agent", "agentic"]),
        ("AI Application Platform", ["copilot", "llm app", "assistant", "platform"]),
        ("Infrastructure", ["inference", "deployment", "sdk", "api", "database"]),
    ]
    for label, keywords in patterns:
        if any(keyword in text for keyword in keywords):
            return label
    return category


def infer_modules(repo: dict[str, Any], category: str) -> list[str]:
    text = words(repo)
    modules = []
    if any(k in text for k in ["agent", "workflow", "orchestration"]):
        modules.extend(["Agent runtime", "Workflow orchestration", "Tool integration"])
    if any(k in text for k in ["rag", "knowledge", "vector", "embedding"]):
        modules.extend(["Knowledge retrieval", "Vector search", "Grounding layer"])
    if any(k in text for k in ["eval", "benchmark", "observability"]):
        modules.extend(["Evaluation harness", "Telemetry", "Quality gates"])
    if any(k in text for k in ["commerce", "retail", "shopping", "recommendation", "product"]):
        modules.extend(["Product intelligence", "Recommendation engine", "Commerce workflow"])
    if not modules:
        modules = [category, "Core library", "Integration surface"]
    return list(dict.fromkeys(modules))[:5]


def infer_scenarios(repo: dict[str, Any], category: str) -> list[str]:
    text = words(repo)
    scenarios = []
    if "agent" in text:
        scenarios.append("Build task-oriented AI agents with tool use and planning.")
    if any(k in text for k in ["commerce", "retail", "shopping", "product"]):
        scenarios.append("Improve AI shopping discovery, product comparison, and conversion assistance.")
    if any(k in text for k in ["enterprise", "workflow", "copilot"]):
        scenarios.append("Automate enterprise workflows and internal knowledge operations.")
    if any(k in text for k in ["rag", "knowledge", "vector"]):
        scenarios.append("Ground agent answers with private knowledge and searchable evidence.")
    if not scenarios:
        scenarios.append(f"Track as a {category.lower()} reference for platform capability planning.")
    return scenarios[:4]


def infer_risk_flags(repo: dict[str, Any], modules: list[str], days_since_push: int) -> list[str]:
    text = words(repo)
    module_text = " ".join(modules).lower()
    flags = []
    license_info = repo.get("license")
    if not license_info:
        flags.append("license unknown")
    if not any(k in text for k in ["doc", "example", "starter", "template", "quickstart"]):
        flags.append("docs need review")
    if days_since_push > 30:
        flags.append("maintenance freshness risk")
    if not any(k in text for k in ["permission", "audit", "policy", "governance", "approval", "security"]):
        flags.append("enterprise control gap")
    if "evaluation" not in module_text and not any(k in text for k in ["eval", "benchmark", "test", "observability"]):
        flags.append("quality gate unclear")
    return flags[:4]


def follow_up_next_action(repo: "Repo") -> str:
    if repo.action_level == "strategic watch":
        return "Assign owner to track releases, ecosystem adoption, license posture, and architecture fit weekly."
    if repo.action_level == "prototype pattern":
        return "Extract the reusable architecture pattern and create a small Leap OS prototype brief."
    if repo.action_level == "clone and test":
        return "Run locally, document setup friction, core modules, integration surface, and operational risks."
    if repo.action_level == "read docs":
        return "Review docs for API shape, deployment model, license, and reusable design ideas."
    if repo.action_level == "monitor":
        return "Keep on watchlist until adoption, docs, or implementation fit improves."
    return "No follow-up unless it reappears with stronger activity or strategic relevance."


def leap_notes(repo: dict[str, Any], category: str, modules: list[str]) -> tuple[str, str]:
    module_text = ", ".join(modules[:3]).lower()
    commerce = (
        "Useful for Leap Agent Commerce OS as a reference for product discovery, shopping copilots, "
        "merchant automation, or conversion-oriented agent workflows."
        if "commerce" in category.lower() or any(k in module_text for k in ["product", "recommendation", "commerce"])
        else "Review for reusable agent runtime, retrieval, or evaluation patterns that can strengthen commerce agents."
    )
    enterprise = (
        "Useful for Leap Agentic Enterprise OS as a pattern for workflow orchestration, enterprise copilots, "
        "knowledge automation, permissions, and operational governance."
        if "enterprise" in category.lower() or any(k in module_text for k in ["workflow", "knowledge", "tool"])
        else "Review for infrastructure and quality-gate ideas that can improve enterprise agent reliability."
    )
    return commerce, enterprise


def rubric_scores(
    repo: dict[str, Any],
    category: str,
    modules: list[str],
    relevance: int,
    report_date: date | None = None,
) -> tuple[int, int, int, str]:
    as_of = report_date or date.today()
    text = words(repo)
    module_text = " ".join(modules).lower()
    commerce_hits = [
        any(k in text for k in ["shopping", "shopper", "checkout", "comparison", "recommendation"]),
        any(k in text for k in ["merchant", "catalog", "merchandising", "retail", "support"]),
        any(k in text for k in ["product", "price", "pricing", "inventory", "review"]),
        any(k in module_text for k in ["agent runtime", "workflow", "tool integration", "commerce workflow"]),
        any(k in module_text for k in ["evaluation", "telemetry", "quality", "grounding"]),
    ]
    enterprise_hits = [
        any(k in text for k in ["workflow", "orchestration", "handoff", "automation"]),
        any(k in text for k in ["knowledge", "rag", "document", "retrieval", "vector"]),
        any(k in text for k in ["connector", "integration", "api", "sdk", "tool"]),
        any(k in text for k in ["permission", "audit", "policy", "governance", "approval"]),
        any(k in module_text for k in ["evaluation", "telemetry", "quality", "deployment"]),
    ]
    commerce_score = sum(3 if hit else 0 for hit in commerce_hits)
    enterprise_score = sum(3 if hit else 0 for hit in enterprise_hits)
    if category == "AI Commerce":
        commerce_score = min(15, commerce_score + 3)
    if category == "Agentic Enterprise":
        enterprise_score = min(15, enterprise_score + 3)
    maturity = min(repo_stars(repo) // 250, 8)
    freshness = 4 if repo.get("pushed_at", "")[:10] >= (as_of - timedelta(days=14)).isoformat() else 0
    strategic_score = min(100, relevance + commerce_score * 2 + enterprise_score * 2 + maturity + freshness)
    if strategic_score >= 80:
        action = "strategic watch"
    elif strategic_score >= 65:
        action = "prototype pattern"
    elif strategic_score >= 50:
        action = "clone and test"
    elif strategic_score >= 35:
        action = "read docs"
    elif strategic_score >= 20:
        action = "monitor"
    else:
        action = "ignore"
    return commerce_score, enterprise_score, strategic_score, action


def trend_metrics(
    item: dict[str, Any],
    report_date: date,
    relevance: int,
    strategic_score: int,
) -> tuple[int, int, float, float, int, str, str]:
    created_date = parse_github_date(item.get("created_at") or "", report_date)
    pushed_date = parse_github_date(item.get("pushed_at") or "", created_date)
    age_days = max(1, (report_date - created_date).days)
    days_since_push = max(0, (report_date - pushed_date).days)
    stars = repo_stars(item)
    forks = repo_forks(item)
    stars_per_day = stars / age_days
    fork_ratio = forks / stars if stars else 0.0
    freshness_score = max(0, 30 - min(days_since_push, 30))
    velocity_score = min(40, int(stars_per_day * 4))
    adoption_score = min(15, int(fork_ratio * 100))
    fit_score = min(15, int((relevance + strategic_score) / 10))
    momentum_score = min(100, velocity_score + freshness_score + adoption_score + fit_score)

    if stars >= 20000 or forks >= 3000:
        maturity_level = "ecosystem leader"
    elif stars >= 5000 or forks >= 800:
        maturity_level = "established"
    elif stars >= 1000 or stars_per_day >= 20:
        maturity_level = "scaling"
    else:
        maturity_level = "emerging"

    if days_since_push <= 7:
        activity = "actively maintained"
    elif days_since_push <= 30:
        activity = "recently active"
    else:
        activity = "needs maintenance review"
    repository_review = (
        f"{maturity_level.title()} project with {stars_per_day:.1f} stars/day, "
        f"{activity}, and {momentum_score}/100 momentum. "
        f"Review first for reusable modules if action is '{item.get('_action_level', 'monitor')}'."
    )
    return age_days, days_since_push, stars_per_day, fork_ratio, momentum_score, maturity_level, repository_review


def normalize_repo(item: dict[str, Any], report_date: date | None = None) -> Repo:
    as_of = report_date or date.today()
    category, relevance = classify(item, as_of)
    subcategory = infer_subcategory(item, category)
    modules = infer_modules(item, category)
    scenarios = infer_scenarios(item, category)
    commerce, enterprise = leap_notes(item, category, modules)
    commerce_score, enterprise_score, strategic_score, action_level = rubric_scores(item, category, modules, relevance, as_of)
    item["_action_level"] = action_level
    age_days, days_since_push, stars_per_day, fork_ratio, momentum_score, maturity_level, repository_review = trend_metrics(
        item, as_of, relevance, strategic_score
    )
    risk_flags = infer_risk_flags(item, modules, days_since_push)
    repo = Repo(
        name=item.get("name") or "",
        full_name=item.get("full_name") or "",
        owner=repo_owner(item),
        url=repo_url(item),
        description=(item.get("description") or "No description provided.").strip(),
        language=item.get("language") or "Unknown",
        stars=repo_stars(item),
        forks=repo_forks(item),
        topics=list(item.get("topics") or []),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
        pushed_at=item.get("pushed_at") or "",
        category=category,
        subcategory=subcategory,
        relevance=relevance,
        modules=modules,
        scenarios=scenarios,
        risk_flags=risk_flags,
        follow_up_next_action="",
        commerce_score=commerce_score,
        enterprise_score=enterprise_score,
        strategic_score=strategic_score,
        action_level=action_level,
        age_days=age_days,
        days_since_push=days_since_push,
        stars_per_day=round(stars_per_day, 2),
        fork_ratio=round(fork_ratio, 4),
        momentum_score=momentum_score,
        maturity_level=maturity_level,
        repository_review=repository_review,
        leap_commerce=commerce,
        leap_enterprise=enterprise,
    )
    repo.follow_up_next_action = follow_up_next_action(repo)
    return repo
