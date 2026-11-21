# Codex Project Instruction

After making relevant changes for this project, commit and push them by running:

```powershell
.\scripts\auto_commit.ps1 -Message "Codex checkpoint: <short summary>"
```

The script pushes the current branch to `origin` by default. Use `-NoPush` only when the user explicitly requests a local-only checkpoint.

If Git is not installed or not on PATH, report that the commit step is blocked. If pushing fails, report the error and leave the local commit intact for retry.

