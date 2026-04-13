# AI Guardrails Setup Guide

How to share the ai-guardrails agent with another user on another computer.

---

## Complete File List

The ai-guardrails feature requires **3 categories** of files:

### Category 1 — Agent + Rules
| File | Purpose |
|------|---------|
| `~/.claude/agents/ai-guardrails.md` | The subagent Claude Code invokes |
| `~/.claude/CLAUDE.md` | User-level rules that trigger ai-guardrails |

### Category 2 — Hook Scripts
| File | Purpose |
|------|---------|
| `~/.claude/scripts/session_start_reminder.py` | Fires RESTORE reminder at session start |
| `~/.claude/scripts/end_reminder.py` | Reminds Claude to run END phase when done |
| `~/.claude/scripts/checkpoint_memory.py` | Saves memory before context compaction |
| `~/.claude/scripts/export_conversation.py` | Exports conversation before compaction |
| `~/.claude/scripts/relocate_plan.py` | Ensures plan files land in `docs/plans/` |

### Category 3 — settings.json hooks config
Wires the scripts to Claude Code's event system.

---

## Prerequisites

The other computer must have **Claude Code** installed:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

---

## Step 1 — Copy the Agent File

```bash
# On the receiving computer:
mkdir -p ~/.claude/agents

scp yourusername@sourcemac:~/.claude/agents/ai-guardrails.md \
    ~/.claude/agents/ai-guardrails.md
```

---

## Step 2 — Copy or Merge CLAUDE.md

### If the other computer has NO existing `~/.claude/CLAUDE.md`

```bash
scp yourusername@sourcemac:~/.claude/CLAUDE.md ~/.claude/CLAUDE.md
```

### If the other computer ALREADY HAS a `~/.claude/CLAUDE.md`

**Do NOT overwrite** — merge instead. Add this block into their existing file:

```markdown
## ai-guardrails Agent

Always trigger the `ai-guardrails` subagent proactively at these moments:

| Trigger | Phase |
|---------|-------|
| Session start (a SessionStart hook already fires a reminder — do not skip) | RESTORE |
| MEMORY.md missing for the current project | ONBOARD |
| User states a new coding goal | START |
| ~10+ tool calls mid-task, or user says "checkpoint" / "save state" | CHECKPOINT |
| Small edit, typo fix | QUICK-CHECK |
| Code changes completed / user says "done" | END |

## MEMORY.md Rules

- MEMORY.md is **auto-injected into every session** — never call `Read` on it; it is already in context
- It is the primary working memory: check ACTIVE and INPROGRESS sections before reading any other file
- If INPROGRESS is filled, surface it immediately as `RESUMING IN-PROGRESS TASK` before anything else
- If MEMORY.md is missing → run ONBOARD to create it

## Plan Files

- Implementation plans live in `docs/plans/YYYY-MM-DD-<slug>.md` inside the project root
- Plans track their own progress via `- [ ]` / `- [x]` checkboxes and a `# Progress:` header
- START creates the plan file; CHECKPOINT marks completed tasks; END marks all done
- RESTORE reads only the first 15 lines of the plan file to find the resume point
```

---

## Step 3 — Copy Hook Scripts

```bash
# On the receiving computer:
mkdir -p ~/.claude/scripts

scp yourusername@sourcemac:~/.claude/scripts/session_start_reminder.py \
    ~/.claude/scripts/

scp yourusername@sourcemac:~/.claude/scripts/end_reminder.py \
    ~/.claude/scripts/

scp yourusername@sourcemac:~/.claude/scripts/checkpoint_memory.py \
    ~/.claude/scripts/

scp yourusername@sourcemac:~/.claude/scripts/export_conversation.py \
    ~/.claude/scripts/

scp yourusername@sourcemac:~/.claude/scripts/relocate_plan.py \
    ~/.claude/scripts/
```

Or copy the entire scripts folder at once:

```bash
scp -r yourusername@sourcemac:~/.claude/scripts ~/.claude/
```

---

## Step 4 — Configure settings.json Hooks

Open (or create) `~/.claude/settings.json` on the receiving computer and add the `hooks` section. 

> ⚠️ **Note the Python path**: the example uses `/opt/homebrew/bin/python3` (Apple Silicon Mac with Homebrew). Adjust to match the receiving computer:
> - Apple Silicon Mac: `/opt/homebrew/bin/python3`
> - Intel Mac / Linux: `/usr/local/bin/python3` or just `python3`
> - Find the right path: `which python3`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/opt/homebrew/bin/python3 '/Users/THEIR_USERNAME/.claude/scripts/session_start_reminder.py'"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/opt/homebrew/bin/python3 '/Users/THEIR_USERNAME/.claude/scripts/end_reminder.py'"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto",
        "hooks": [
          {
            "type": "command",
            "command": "/opt/homebrew/bin/python3 '/Users/THEIR_USERNAME/.claude/scripts/checkpoint_memory.py' && python '/Users/THEIR_USERNAME/.claude/scripts/export_conversation.py'"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "/opt/homebrew/bin/python3 '/Users/THEIR_USERNAME/.claude/scripts/relocate_plan.py'"
          }
        ]
      }
    ]
  }
}
```

Replace `THEIR_USERNAME` with the actual username on the receiving computer (`whoami` to find it).

> ⚠️ If `settings.json` already has other content, merge the `hooks` block into the existing JSON — do not overwrite the whole file.

---

## Step 5 — Verify

Open Claude Code in any project:

```bash
cd ~/any-project
claude
```

At session start you should see ai-guardrails run RESTORE automatically:

```
## RESTORE Result
Session restored.
- Goal: NONE | Status: NONE (clean session)
```

---

## What Each Hook Does

| Hook event | Script | Why it matters |
|------------|--------|----------------|
| **SessionStart** | `session_start_reminder.py` | Injects the RESTORE reminder so Claude reads MEMORY.md before doing anything |
| **Stop** | `end_reminder.py` | Prompts Claude to run END phase and update docs before closing |
| **PreCompact** | `checkpoint_memory.py` + `export_conversation.py` | Preserves in-progress work before Claude Code auto-compacts the context window |
| **PostToolUse (Write)** | `relocate_plan.py` | Automatically moves plan files to `docs/plans/` if written elsewhere |

---

## How It Works on Existing Projects

| Scenario | What happens |
|----------|-------------|
| **New project** | Creates `MEMORY.md` + `docs/PROJECT_GUIDE.md` from scratch |
| **Existing project, first session** | Bootstraps docs by reading existing codebase and git history |
| **Existing project, later sessions** | Normal RESTORE — reads `MEMORY.md`, continues where it left off |

The bootstrap is **non-destructive** — only creates new files, never modifies existing code.

---

## Optional: claudeception Skill

Captures reusable knowledge from debugging sessions and creates skills automatically.

```bash
# Copy the skill
scp -r yourusername@sourcemac:~/.claude/skills/claudeception \
    ~/.claude/skills/

# Copy the hook script
mkdir -p ~/.claude/hooks
scp yourusername@sourcemac:~/.claude/hooks/claudeception-activator.sh \
    ~/.claude/hooks/

chmod +x ~/.claude/hooks/claudeception-activator.sh
```

Then add to `settings.json` hooks:

```json
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "/Users/THEIR_USERNAME/.claude/hooks/claudeception-activator.sh"
      }
    ]
  }
]
```

This is optional — ai-guardrails works fully without it.
