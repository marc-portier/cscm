---
trigger: always_on
---

# Language Policy

## Overview
This project targets both local practitioners (Belgian lifeguard stations) and the international open-source and open-water swimming community across the English Channel and North Sea (BE, NL, FR, UK).

## Rules

### 1. Public Repository Assets Must Be in English (EN)
All artifacts that are tracked in Git and published to GitHub MUST be written in **English**:
* **Documentation**: All files under `docs/` (including `plans.md`, `history.md`, and any files in `docs/experiments/`).
* **Design & Version Changelogs**: Any `versions.md` or design documentation.
* **Source Code**: Python code, docstrings, variable names, log messages, exception messages, and comments.
* **Tests**: Test names, assertions, and test docstrings.
* **Git History**: Commit messages, PR descriptions, and issue templates.

### 2. Pair-Programming Conversation in User Preferred Language
* Direct conversational interaction with the user (chat messages, questions, and turn-by-turn explanations) remains in the preference of the local user (i.e. **Dutch (NL) for Marc**) by default. Users can express this in a local (excluded from github rule) matching `.agents/rules/local**md`

### 3. Clean Plaintext & Unicode in Chat (No Raw LaTeX Delimiters)
* **Do NOT use LaTeX math delimiters (`$...$` or `$$...$$`) in chat messages**: The Antigravity chat panel does not render KaTeX/MathJax, causing raw LaTeX (e.g. `$\Delta s$`, `$\approx$`, `\text{km/u}`) to appear as cluttered, unreadable text in the chat UI.
* **Use Unicode and readable typography in chat**: Use standard unicode symbols (e.g. `≈`, `Δ`, `√`, `²`, `³`, `→`, `·`, `±`) and standard plain units (e.g. `17.2 m/s`, `62 km/u`, `Δt = 10 - 15 min`).
* **Keep LaTeX for Persistent Documents**: Mathematical LaTeX formatting is welcome in persistent documentation files (`.md` in `docs/` or `experimenting/`), where markdown previewers and GitHub render it with KaTeX.

