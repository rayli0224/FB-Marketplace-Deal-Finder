# create-pr

A PR already exists for the current branch. Find it and modify it using MCP (do not create a new PR). There is no PR template; use a concise, bullet-pointed description.

## Title rules
- Start with bracketed topics (e.g. `[Results] [SSE]`).
- Follow with a short, imperative description of the change.
- Use only plain text: no HTML, no comment syntax, no other symbols (e.g. `<!-- -->`). For multiple logical changes, use "and" or a comma (e.g. `[Auth] In-app login and session-expiry handling`).

## Description rules
- Use **only** changes introduced in this branch.
- Include **only user-facing changes**: what the end user of the product will see or experience and why it matters. Omit developer-only changes (e.g. cleanup commands, tooling, config, refactors that don’t change behavior).
- Do **not** list implementation details. Do not mention files, functions, refactors, or how the code was built.
- Write in **plain English** with bullet points. Each bullet should stand on its own.
- Avoid change logs, file listings, and step-by-step implementation lists.
- Avoid vague or generic language. Preserve wording from the product or UI when it helps.
- If related PRs exist, link them explicitly (e.g. `#123`); omit the section if none.

## Testing
- Describe **how the code was tested**, not how tests are written.
- Do NOT mention test syntax, frameworks, helpers, or formatting.
- Focus on the validation approach (e.g. manual flows, automated coverage, edge cases exercised).

## Process
- **Check git status** — If there are uncommitted changes, commit them with a message matching the PR title (or a reasonable default).
- **Push branch if needed** — Check if the current branch exists on the remote. If not, push it with `git push -u origin <branch-name>`. If the branch exists but is behind, push any local commits.
- **Find or create PR** — Look for an existing PR for the current branch using MCP (e.g. `list_pull_requests` with `head` filter: `owner:branch-name`, state `open`).
  - If a PR exists, **modify** it using MCP: set title and body via `update_issue` (PRs are issues; use the PR number as the issue number).
  - If no PR exists, **create** one using `create_pull_request` with the title and body.
- When the user asks to do it or update the PR, look up the repo owner from the remote (e.g. `origin`), then push if needed and find/update/create the PR.
