"""Core data model: paths/config constants and the Repo dataclass — the single contract that flows through collect, enrich, store, and render."""
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

ROOT = Path(__file__).resolve().parents[2]  # scripts/ghstar/model.py -> repo root
REPORTS = ROOT / "reports"
PUBLIC = ROOT / "public"
DATA_DIR = PUBLIC / "data"
DEFAULT_DB = Path(os.environ.get("GHSTAR_DB", ROOT / "data" / "ghstar.sqlite"))

FOCUS_AREAS = {
    "AI Agent Framework": [
        "agent",
        "multi-agent",
        "autonomous agent",
        "tool calling",
        "workflow",
        "llm app",
    ],
    "Agentic Enterprise": [
        "enterprise",
        "workflow automation",
        "rag",
        "knowledge base",
        "copilot",
        "orchestration",
    ],
    "AI Commerce": [
        "commerce",
        "ecommerce",
        "shopping",
        "retail",
        "recommendation",
        "product search",
    ],
    "AI Infrastructure": [
        "inference",
        "vector database",
        "embedding",
        "observability",
        "evaluation",
        "deployment",
    ],
}

SEARCH_QUERIES = [
    'agent language:Python',
    'multi-agent',
    'llm agent',
    'autonomous agent',
    'ai workflow',
    'rag agent',
    'agentic enterprise',
    'ai ecommerce',
    'ai commerce',
    'retail ai',
    'recommendation system ai',
    'product search ai',
    'copilot enterprise',
    'tool calling llm',
    'ai evaluation',
]


@dataclass
class Repo:
    name: str
    full_name: str
    owner: str
    url: str
    description: str
    language: str
    stars: int
    forks: int
    topics: list[str]
    created_at: str
    updated_at: str
    pushed_at: str
    category: str
    subcategory: str
    relevance: int
    modules: list[str]
    scenarios: list[str]
    risk_flags: list[str]
    follow_up_next_action: str
    commerce_score: int
    enterprise_score: int
    strategic_score: int
    action_level: str
    age_days: int
    days_since_push: int
    stars_per_day: float
    fork_ratio: float
    momentum_score: int
    maturity_level: str
    repository_review: str
    leap_commerce: str
    leap_enterprise: str
