# Adaptive Collaboration Patterns & Design Exploration

## Overview
This project thrives on rapid, iterative co-design between Marc (human domain expert / coastal swimmer) and the AI agent. To navigate complex hydrodynamic kinematics and rich information graphics effectively, two high-impact collaboration patterns have proven exceptionally productive and should be actively leveraged and suggested.

---

## Proven Collaboration Patterns

### 1. Guided Q&A & Socratic Interview Mode (Chunked Dialectic)
* **Context**: Ideal when addressing multi-layered architectural decisions, ambiguous design spaces, data contract definitions, or when the user is in low-bandwidth / focused environments (e.g., attending meetings or reviewing on mobile).
* **Agent Behavior**:
  * **Chunking**: Break complex, multi-variable topics into **digestible, sequential mini-dialogues** (1–3 focused questions or options at a time). Avoid monolithic walls of text.
  * **Low-Friction Responses**: Structure questions so they can be answered quickly with minimal cognitive overhead (e.g., choosing "Option 1" or typing a couple of keywords).
  * **Continuous Synthesis**: Synthesize agreed points continuously and capture them in persistent architectural sub-plans.
  * **Proactive Suggestion**: The agent should actively propose: *"Would you like to tackle this via a quick guided Q&A session in small steps?"* whenever confronting broad, multi-faceted design decisions.

---

### 2. Visual Ingestion of reMarkable Hand-Notes & Sketches
* **Context**: Essential when spatial geometry, visual layouts, or mathematical transforms are faster to draw than to articulate in prose (e.g., coordinate inversions, space-time transforms, vector cards, turnaround buffers).
* **Agent Behavior**:
  * The user regularly shares hand-drawn diagrams, mathematical derivations, or layout mockups exported from a reMarkable tablet (PDF / PNG).
  * The agent proactively slices, crops, analyzes, and translates these handwritten visual artifacts into exact mathematical equations, SVG vector paths, and data models.
  * **Proactive Suggestion**: When textual descriptions become abstract or spatially ambiguous, the agent should freely suggest: *"Feel free to drop a quick reMarkable sketch if that's faster to illustrate the spatial intuition!"*

---

### 3. Asynchronous Inline Code Annotations & Review Markers (`# REVIEW:`)
* **Context**: Ideal during code reviews, architectural audits, and pair-programming iterations where the user navigates the codebase directly in the IDE and annotates specific lines without modal interruptions.
* **Protocol**:
  * **User Annotations**: The user places `# REVIEW: <question, suggestion, critique>` directly above or on the relevant code lines.
  * **File Completion Marker**: When a file review is complete, the user marks the end of the file with `# REVIEW: done` (or `# REVIEW: ready`).
  * **Agent Sweep & Refactor**: The agent searches for all `# REVIEW:` tags (`grep_search`), synthesizes the feedback, implements the refactorings, removes the resolved markers, and validates with automated tests.
  * **Persistence**: Architectural changes or trade-offs stemming from the review are captured in the relevant documentation or sub-plans.

---

## 4. Dynamic Workflow Selection
The agent and user should mutually select the most effective mode for the challenge at hand:
* **Deep Code Refactoring / Implementation**: Focused autonomous sprints with automated test validation.
* **Architecture & Data Contract Design**: Guided Q&A dialogue followed by formal markdown sub-plans.
* **Interactive Code Review**: Asynchronous `# REVIEW:` marker sweeps across files in IDE.
* **Graphic & UX Ideation**: reMarkable sketch ingestion coupled with fast, iterative SVG/PNG visual verification.
