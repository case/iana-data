---
title: Dependabot cooldown is 7 days
summary: The cooldown on all three Dependabot ecosystems dropped from 14 days to 7, by owner decision.
created: 2026-11-11
author: Eric Case
tags: [log, decision, dependencies, dependabot]
---

# 2026-11-11 - Dependabot cooldown

`.github/dependabot.yaml` sets `cooldown.default-days: 7` for `uv`, `github-actions` and `npm`. It was
14 days from 2025-12-10.

The owner chose 7 days. A version becomes eligible 7 days after its release.

Manual bumps follow the same rule: a version younger than 7 days waits.
