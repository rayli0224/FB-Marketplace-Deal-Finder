# explore

My goal in this session is to {{input}}

Here's how I need you to work with me:

## Hard boundary: read-only — no code changes

**This command is strictly read-only.** No code or config may be changed until the user runs the **implement** command (or switches to Agent mode and asks for implementation).

- **Do not** edit, create, or delete any files.
- **Do not** run commands that change state (e.g. install, build, git commit, git checkout).
- **Only** use read-only tools: read files, search codebase, search the internet, list directories. You may run read-only terminal commands (e.g. `whoami`, `git branch`, `git status`) when needed to answer a question.
- If the user wants to implement what you've explored, tell them to run the **implement** command in Agent mode (or to switch to Agent mode and continue there). Do not apply changes yourself in this command.

## Research and Understand

- **Search the codebase** — Find relevant code, config, and docs. Summarize how things work and where the goal touches the project.
- **Search the internet** — Look up docs, APIs, patterns, or errors that are relevant to the goal.
- **Use other sources** — Check project rules (`.cursor/rules/`), README, or any other place that helps (read-only).

Use this to understand the problem and come up with a concrete solution or plan.

## One Question at a Time

- When you need to clarify something, ask **one clear question** and stop.
- **Wait for the user's answer** before asking the next question or moving on.
- If you have multiple questions, ask the first one only; after they answer, ask the next.
- Do not bundle several questions into one message (e.g. avoid "Do you want X? Also, should we do Y or Z?" — split into separate turns).

## Output

- Help the user understand the problem and propose a solution (or options with trade-offs).
- Keep explanations concise and structured (bullets or short paragraphs).
- When you have enough information, end with a clear summary or recommended next steps (e.g. "Use /implement in Agent mode to apply this.").
