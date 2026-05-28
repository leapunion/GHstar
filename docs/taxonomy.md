# GHstar Repository Taxonomy

## Classification Model

GHstar should use a three-layer taxonomy:

1. Functional category: what kind of repository it is.
2. Capability tags: what reusable building blocks it contains.
3. Learning tags: how Leap Commerce OS or Agentic Enterprise OS can learn from it.

## Functional Categories

| Category | Definition | Common Signals |
| --- | --- | --- |
| AI Agent Framework | Runtime, planning, tool use, multi-agent coordination, or LLM app framework | agent, multi-agent, autonomous agent, tool calling, workflow, LLM app |
| Agentic Enterprise | Enterprise workflow, copilots, knowledge operations, RAG, or orchestration | enterprise, workflow automation, RAG, knowledge base, copilot, orchestration |
| AI Commerce | Shopping, retail, product discovery, recommendation, merchandising, or conversion workflows | commerce, ecommerce, shopping, retail, recommendation, product search |
| AI Infrastructure | Inference, embeddings, vector databases, deployment, evaluation, or observability | inference, vector database, embedding, observability, evaluation, deployment |

## Capability Tags

| Tag | Use When |
| --- | --- |
| Agent runtime | The repo runs agents, manages agent loops, or structures reasoning and action. |
| Workflow orchestration | The repo coordinates multi-step processes, dependencies, retries, or handoffs. |
| Tool integration | The repo connects LLMs or agents to external APIs, tools, browsers, files, or systems. |
| Knowledge retrieval | The repo retrieves private, local, or indexed knowledge for grounded answers. |
| Vector search | The repo includes embeddings, vector databases, semantic search, or similarity ranking. |
| Grounding layer | The repo emphasizes source-backed answers, citations, context construction, or evidence. |
| Evaluation harness | The repo tests agent quality, LLM outputs, workflows, or regression behavior. |
| Telemetry | The repo logs, traces, monitors, or visualizes runtime behavior. |
| Quality gates | The repo enforces checks before deployment, execution, approval, or response delivery. |
| Product intelligence | The repo models products, catalogs, attributes, reviews, prices, or inventory. |
| Recommendation engine | The repo ranks products, content, options, or next-best actions. |
| Commerce workflow | The repo supports shopping, merchandising, checkout, support, or merchant operations. |
| Enterprise copilot | The repo helps employees complete work across enterprise knowledge or systems. |
| Governance and approvals | The repo includes permissions, audit logs, policy checks, human review, or risk controls. |

## Learning Tags

| Tag | Meaning |
| --- | --- |
| Commerce discovery | Helps shoppers or operators find products, content, or choices. |
| Commerce conversion | Improves comparison, decision support, confidence, checkout, or retention. |
| Merchant automation | Automates catalog, merchandising, promotion, support, reporting, or operations work. |
| Enterprise workflow | Automates repeatable internal processes across people, tools, and systems. |
| Enterprise knowledge | Improves retrieval, summarization, document intelligence, or institutional memory. |
| Enterprise governance | Improves permissioning, auditability, approval, policy, or compliance workflows. |
| Agent reliability | Improves evaluation, monitoring, recovery, or production confidence for agents. |
| Platform integration | Provides reusable connectors, APIs, SDKs, or deployment patterns. |

## Scoring Guidance

Use these repository-level scores in future report data:

- `commerce_score`: 0-15, sum of the five Leap Commerce OS rubric dimensions.
- `enterprise_score`: 0-15, sum of the five Agentic Enterprise OS rubric dimensions.
- `strategic_score`: weighted blend of relevance, maturity, freshness, commerce score, and enterprise score.
- `action_level`: ignore, monitor, read docs, clone and test, prototype pattern, or strategic watch.

## Recommended Defaults

- A repository may have one primary functional category and multiple capability or learning tags.
- Prefer observed repository evidence over inferred ambition.
- Use the lowest reasonable score when documentation is thin.
- Keep taxonomy labels stable across days so trend charts remain comparable.
- Add new tags only when at least three repositories need the distinction.
