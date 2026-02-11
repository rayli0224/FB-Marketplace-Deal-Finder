# create-pr

A PR already exists for the current branch. Find it and modify it using MCP (do not create a new PR). There is no PR template; use a concise, bullet-pointed description.

## Title rules
- Start with bracketed topics (e.g. `[Results] [SSE]`).
- Follow with a short, imperative description of the change.
- Use only plain text: no HTML, no comment syntax, no other symbols (e.g. `<!-- -->`). For multiple logical changes, use "and" or a comma (e.g. `[Auth] In-app login and session-expiry handling`).

## Description rules
- Use **only** changes introduced in this branch.
- Write in **plain English**, not as an implementation checklist. Describe what the change does, how it behaves, and why it matters to the reader.
- Use bullet points for readability and to separate distinct ideas. Each bullet should stand on its own.
- Focus on intent and behavior; keep implementation details out of the main bullets.
- Avoid change logs, file listings, or step-by-step implementation lists.
- Avoid vague or generic language. Preserve wording from the code or surrounding context when available.
- If related PRs exist, link them explicitly (e.g. `#123`); omit the section if none.

## Testing
- Describe **how the code was tested**, not how tests are written.
- Do NOT mention test syntax, frameworks, helpers, or formatting.
- Focus on the validation approach (e.g. manual flows, automated coverage, edge cases exercised).

## Process
- **Find** the existing PR for the current branch using MCP (e.g. `list_pull_requests` with `head` filter: `owner:branch-name`, state `open`).
- **Modify** that PR using MCP: set title and body via `update_issue` (PRs are issues; use the PR number as the issue number).
- When the user asks to do it or update the PR, look up the repo owner from the remote (e.g. `origin`), then find and update the PR.
