# create-pr

Edit the existing GitHub Pull Request for the current branch. There is no PR template; use a concise, bullet-pointed description.

## Title rules
- Start with bracketed topics (e.g. `[Results] [SSE]`).
- Follow with a short, imperative description of the change.
- For multiple logical changes: make the title a collection; separate with HTML comments (e.g. `<!-- change 1 -->`, `<!-- change 2 -->`).

## Description rules
- Use **only** changes introduced in this branch.
- The description should be **concise and bullet-pointed for readability**.
- Use bullets by default; avoid paragraphs unless absolutely necessary.
- Capture, at a high level: intent of the change, behavior it enables, meaningful architectural or design implications.
- Incorporate architectural and design reasoning **inline**, not as separate sections.
- Avoid change logs, file listings, or implementation steps.
- Avoid vague or generic language.
- Preserve wording from the code or surrounding context when available.
- If related PRs exist, link them explicitly (e.g. `#123`); omit the section if none.

## Testing
- Describe **how the code was tested**, not how tests are written.
- Do NOT mention test syntax, frameworks, helpers, or formatting.
- Focus on the validation approach (e.g. manual flows, automated coverage, edge cases exercised).

## Process
- Set the PR title and body. When the user asks to do it or update the PR, apply via GitHub API (e.g. update_issue for the PR number) or `gh pr edit` if available.
