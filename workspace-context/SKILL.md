---
name: workspace-context
description: Maintain and apply checked context for a multi-repository workspace. Use when Codex is working from a shared parent directory containing multiple projects and needs to reuse recently learned repository knowledge, update workspace-local context, check whether stored context is stale by comparing branches or commit ids, record current focus areas, or avoid broad repeated codebase investigation while still validating assumptions against current code.
---

# Workspace Context

## Purpose

Use this skill to maintain workspace-local repository context. Keep this global skill generic; store project-specific facts only in the current workspace's `.codex/workspace-context/` directory.

Keep the skill portable. Do not hard-code the user's home directory, repository root, or this skill's installation path. Resolve bundled resources relative to the directory containing this `SKILL.md`. Resolve workspace files relative to the discovered workspace root.

## Boundary

Use `.codex/workspace-context/` as Codex working memory, not as the destination for user-facing deliverables.

Store only:

- investigation indexes
- repo roles and entry points
- current focus and open questions
- freshness metadata such as branch, commit, date, and dirty state
- durable findings that help future Codex sessions avoid broad rediscovery
- links to user-facing documents created elsewhere

Do not store:

- final reports requested by the user
- design docs meant for humans to read directly
- markdown deliverables
- generated analysis tables whose primary audience is the user
- project documentation that should live in the repository's normal docs tree
- raw transcripts, long command outputs, or copied source excerpts

When the user asks to "output a markdown document", "write a report", "create docs", or similar, write the deliverable into the project workspace, such as `docs/`, the relevant repo's documentation directory, or another explicit user-provided path. Then update `.codex/workspace-context/` only with a short index entry pointing to that document.

## Context Location

From the current working directory, walk upward until finding:

```text
.codex/workspace-context/index.md
```

Use that directory as the context store. If it does not exist, stop and ask before creating it. Do not use fallback paths unless the user explicitly requests one.

Treat the parent directory of `.codex/` as the workspace root. Refer to workspace files with paths relative to that root.

Expected layout:

```text
.codex/workspace-context/
├── index.md
├── repos/
├── focus/
│   ├── current.md
│   └── history.md
└── snapshots/
    └── latest.md
```

Do not add task deliverables to this layout. Add only context files that help future investigation.

## Default Workflow

1. Read `.codex/workspace-context/index.md` first.
2. Identify the relevant repository or repositories for the user's task.
3. Read `.codex/workspace-context/focus/current.md` when recent priorities may matter.
4. For repo-specific work, read only the relevant `.codex/workspace-context/repos/<repo-name>.md` files.
5. Check the current branch and HEAD before trusting recorded recent context.
6. Use stored context to narrow investigation, then verify code for behavior-sensitive or implementation-sensitive decisions.
7. Update the smallest relevant context file after durable discoveries.
8. If the task produced a user-facing artifact, store the artifact outside `.codex/workspace-context/` and record only its path and short purpose in context.

## Freshness Rules

Classify stored notes by freshness:

- `stable`: background facts such as repo purpose, major directories, build system, long-lived architecture boundaries.
- `recent`: implementation findings tied to a branch and commit.
- `volatile`: temporary failures, dirty working tree observations, bug symptoms, unmerged work, or assumptions from partial investigation.

When recorded and current commit differ:

- Keep `stable` notes as orientation.
- Treat `recent` notes as stale until targeted files are re-read.
- Treat `volatile` notes as invalid until reproduced.
- Update `Last Checked` only after inspecting enough code or command output to justify the change.

When the working tree is dirty:

- Mention dirty status before relying on context.
- Do not overwrite notes about user changes unless the user asks.
- Record dirty status in snapshots, not as a permanent repo fact unless it explains current focus.

## Updating Policy

Update context when one of these happens:

- A new repository's purpose, build system, or test entry points are established.
- A module boundary, ownership boundary, state machine, or recurring architectural pattern is confirmed.
- A repeated build, test, debug, deployment, or data command is validated.
- A current focus changes.
- A stale or wrong note is discovered.
- The user explicitly asks to remember workspace context.

Prefer replacing stale notes with corrected topic summaries over appending long logs. Keep evidence as paths, commands, commit ids, and dates.

If a useful result is also a user-facing deliverable, keep the complete result in the project documentation location and keep only a compact pointer in workspace context.

## Repository Context Format

Create or update `.codex/workspace-context/repos/<repo-name>.md` with:

```md
# <repo-name>

## Last Checked

- workspace path:
- branch:
- commit:
- date:
- dirty:

## Stable Context

- ...

## Recent Findings

### YYYY-MM-DD, commit <short-sha>

- ...

## Known Commands

- ...

## Volatile Notes

- ...
```

## Snapshot Script

From the workspace root, run:

```bash
python3 <this-skill-dir>/scripts/snapshot_repos.py --root . --output .codex/workspace-context/snapshots/latest.md
```

Resolve `<this-skill-dir>` from the actual location of the loaded `workspace-context` skill. Do not replace it with a hard-coded machine-specific path in persistent docs.

Use `--max-depth` when repositories are deeper than the default scan depth.

## Portability Rules

- In `SKILL.md`, use paths relative to the skill directory for bundled scripts, references, and assets.
- In workspace context files, use paths relative to the workspace root.
- In generated project docs, use paths relative to the repository or workspace unless the user explicitly asks for absolute paths.
- Do not persist `/home/...`, `/Users/...`, container paths, or temporary paths in reusable context unless the path itself is the subject of the task.
