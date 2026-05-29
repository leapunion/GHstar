# 90-Day Top Star Radar

GHstar now treats the default report as a 90-day radar for AI, Agent, Commerce, and Enterprise repositories.

## Analysis Dimensions

- Category distribution: AI Agent Framework, Agentic Enterprise, AI Commerce, and AI Infrastructure.
- Language distribution: dominant implementation stacks in the radar window.
- Activity: repositories pushed in the last 7 and 30 days.
- Star velocity: total stars divided by repository age in days.
- Fork ratio: forks divided by stars as a lightweight reuse/adoption proxy.
- Momentum score: star velocity, push freshness, fork ratio, and Leap strategic fit.
- Maturity level: emerging, scaling, established, or ecosystem leader.
- Repository review: generated short commentary explaining maturity, activity, momentum, and inspection priority.

## Current Limitation

GitHub Search API returns current star totals, not historical star deltas. `stars_per_day` is therefore a growth proxy based on repository age, not a true 90-day star delta. For exact star growth, add a scheduled stargazer-history collector or a third-party GitHub trend dataset.
