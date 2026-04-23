# Workspace Context Store Template

Create this under the workspace root as `.codex/workspace-context/`.

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

Keep `index.md` short. Put repository facts in `repos/`. Put active task priorities in `focus/current.md`. Archive compressed older priorities in `focus/history.md`.
