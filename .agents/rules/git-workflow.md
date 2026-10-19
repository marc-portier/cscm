---
trigger: always_on
---

# Git Workflow & Commit Policy

## Overview
All git commits and pushes are strictly executed by the human user. Antigravity/agents must never execute `git commit` or `git push` directly.

## Guidelines for Agents

1. **Human-Only Commits & Pushes**:
   - The agent may inspect git status (`git status`, `git diff`, `git log`) 
   - The agent should request permission to stage files (`git add`) when preparing changes, and/or suggest when the user should do so.
   - The final `git commit` and `git push` operations must always be performed by the user.

2. **Proactive Atomic Guardian**:
   - The agent should actively help monitor that changes remain **atomic** — focused on a single topic, feature, or fix.
   - When a logical unit of work is completed (e.g., a backlog issue is implemented and tested), the agent should:
     - Prompt the user to conclude and commit the change.
     - Propose a clean, conventional commit message (e.g. `feat: ...`, `fix: ...`, `docs: ...`).
     - Avoid accumulating unrelated modifications across multiple tracks into a single massive uncommitted diff.
     - Help grouping and structuring over different git branches to help achieve this.
