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
- Fill in the existing template using **only** changes introduced in this branch.
- The description should be **concise and bullet-pointed for readability**.
- Use bullets by default; avoid paragraphs unless absolutely necessary.
- Capture, at a high level:
  - the intent of the change
  - the behavior it enables
  - any meaningful architectural or design implications
- Incorporate architectural and design reasoning **inline**, not as separate sections.
- Avoid change logs, file listings, or implementation steps.
- Avoid vague or generic language.
- Preserve wording from the code or surrounding context when available.
- Remove unused or empty portions of the template rather than inventing content.
- If related PRs exist, link them explicitly (e.g. `#123`); remove the section entirely if none apply.

## Testing section rules
- Describe **how the code was tested**, not how tests are written.
- Do NOT mention test syntax, frameworks, helpers, or formatting.
- Focus on the validation approach (e.g. manual flows, automated coverage, edge cases exercised).

## Process
- Output only the proposed edits to the existing title and PR body.
- Wait for approval before applying changes.

