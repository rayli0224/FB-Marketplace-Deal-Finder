# create-pr

You are editing the existing GitHub Pull Request description for the current branch.

The PR description already contains a GitHub template.  

You MUST use the existing template exactly as-is.  

Do NOT create a new structure, sections, or document.

## Hard constraints

- Do NOT create any new files or markdown documents.

- Do NOT draft content in a separate file.

- Do NOT add new section headers.

- Only replace or remove text inside the existing PR template.

- Propose edits inline only.

- Do NOT apply changes until I explicitly approve.

## Title rules

- Edit the existing PR title.

- Start with bracketed topics (e.g. `[Axion] [Asset Library]`).

- Follow with a short, imperative description of the change.

- **If there are multiple logical changes**:

  - Make the title a **collection of those changes**

  - Separate each change using HTML comments  

    (e.g. `<!-- change 1 -->`, `<!-- change 2 -->`).

## Description rules

- Fill in the existing template content using **only** the code changes introduced in this branch.

- Provide a **high-level architectural overview**, not a change log.

- Emphasize **why** the change exists and the behavior it enables.

- Include **what** changed only insofar as it supports the rationale.

- **Use bullet points by default**, especially when describing multiple logical changes.

- Avoid listing individual functions, files, hooks, or implementation steps.

- Focus on intent, system behavior, and architectural direction.

- Avoid vague or generic language.

- Preserve wording from the code/context when available; do not infer from branch name.

- Remove any unused or empty portions of the template rather than inventing content.

- If any related PRs exist, they MUST be linked explicitly (e.g. `#123`, `#456`) using the existing template; remove the section entirely if none apply.

## Process

- Output only the proposed edits to the existing title and PR body.

- Wait for approval before applying changes.
