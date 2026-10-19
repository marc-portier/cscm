# Terminal Command Policy & Interactive Communication

## Overview
The user manually approves terminal commands in the IDE. To prevent unnecessary authorization prompts and keep workflows smooth, follow these rules regarding terminal commands and context gathering.

## Guidelines

### 1. Ask Before Running Exploratory Shell Commands
- Do NOT run shell commands solely to discover environment state (e.g. `which python`, `poetry env info`, `git status`, package versions, active containers) if you can simply ask the user in chat.
- If context about the environment, configuration, or recent runs is needed, ask the user directly first.

### 2. Prefer Non-Terminal Inspection Tools
- For exploring the codebase, reading files, or finding symbols, always prefer internal IDE tools (`view_file`, `grep_search`, `list_dir`) over terminal commands (`cat`, `grep`, `find`, `ls`).
- Internal inspection tools run quietly and do not require manual shell approval prompts.

### 3. Announce & Bundle Execution Commands
- When dynamic execution or testing is required (e.g., `pytest`, running a simulation script):
  - Announce the exact command you intend to run.
  - Ask the user if they would like you to execute it, or if they prefer to run it themselves or have already done so.
  - Avoid chaining multiple individual exploratory shell commands consecutively.

### 4. Leverage User-Supplied Context
- When the user provides context (attached files, error traces, diffs via `@`), treat this information as current and authoritative rather than executing commands to re-verify it.
