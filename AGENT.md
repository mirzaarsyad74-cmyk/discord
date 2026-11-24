# AGENT Guidelines & Build Rules: Discord Release Monitor Bot

## 1. Mandatory Live Workstep Checklist (`update_steps`) for All Tasks
* **Always Display Live Visual Checklist Widget**:
  Whenever executing multi-step tasks, feature implementations, bug fixes, UI adjustments, or releases in this Discord bot workspace, the AI assistant (including Gemini, Claude, and all other models) **MUST ALWAYS call the `update_steps` tool** at the very beginning of the plan to display the interactive live workstep progress checklist widget in the user interface.
* **Synchronize and Progress Live**:
  - Break down the task into 3 to 10 clear, imperative steps relevant to this bot (e.g., "Inspect monitor source files", "Update poster canvas layout", "Add vector icon routines", "Verify local Python syntax", "Generate example poster", "Commit and deploy to Koyeb").
  - Call `update_steps` in parallel with the first tool call of each phase so the checklist renders immediately in the UI without adding extra turns.
  - Dynamically mark completed steps as `done`, the current active step as `in_progress`, and upcoming steps as `pending`.
  - When the final task completes, call `update_steps` one last time with every step marked `done` before writing the final response.

---

## 2. Discord Release Monitor & Steam Top 10 SUO Radar Guidelines
* **Native Pixel-Perfect Vector Icons (No Font Emojis)**:
  Never use raw font emojis (`📚`, `💾`, `🌐`, `⚡`, `👥`, `📦`, `📥`, `★`) in Pillow text rendering on image posters. Always use the built-in `draw_vector_icon()` helper to draw crisp vector icons directly on the canvas to ensure zero tofu missing-character boxes (`▯`) across all operating systems and cloud Linux containers (Koyeb).
* **Hourly Radar Scheduling**:
  Steam Top 10 SUO Radar strictly triggers at the top of clock hours (e.g. 4:00 AM, 5:00 AM, 6:00 AM GMT+8). When bot starts mid-hour, it arms for the upcoming top-of-the-hour.
* **Dual Deployment Pipeline**:
  - Code changes to `main` branch are automatically deployed to Koyeb cloud runner (`https://increasing-saree-yuno74-2b5073cf.koyeb.app`).
  - Always run `python -m py_compile` before committing and pushing to ensure zero syntax or import errors.

