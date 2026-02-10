In `ok-wuthering-waves`, keep `master` synced to `upstream/master`, then merge `master` into `my`. If confidence is low at any point, stop and open an inbox item for manual follow-up.

---

## Steps

### Global rule

`src/` is merge-only.

- Never edit files under `src/` directly.
- `src/` should change only through upstream sync/merge.
- If upstream changes break compatibility, fix `custom/` or top-level automation scripts, not `src/`.
- Codex automation runs in a worktree. If you check out any branch during this flow, detach from the branch before finishing the run.

### (1) Safety check

Run `git status --porcelain`.

- If output is non-empty: open an inbox item listing changes, then stop.
- Do not stash, reset, or edit files.

### (2) Fetch upstream

Run `git fetch upstream`.

### (3) Fast-forward local `master`

Record the pre-sync hash:

```bash
OLD_MASTER=$(git rev-parse master)
```

Then run:

```bash
git switch master
git merge --ff-only upstream/master
```

- If `--ff-only` fails: open an inbox item explaining `master` diverged from `upstream/master`, then stop. Do not force reset.
- If already up to date: stop and archive.

### (4) Push `master` to origin

Run `git push origin master`.

- If push fails (auth, non-FF, other): open an inbox item with the error, then stop.

---

### (5) Pre-merge compatibility check (critical)

Goal: detect upstream task API changes before merging into `my`, and adapt local scripts first.

Watch files:
- `src/task/DailyTask.py`
- `src/task/TacetTask.py`
- `src/task/BaseCombatTask.py`

Run:

```bash
NEW_MASTER=$(git rev-parse master)
WATCH_FILES="src/task/DailyTask.py src/task/TacetTask.py src/task/BaseCombatTask.py"
CHANGED_TASKS=$(git diff --name-only "$OLD_MASTER".."$NEW_MASTER" -- $WATCH_FILES)
printf '%s\n' "$CHANGED_TASKS"
```

Decision:
1. If `CHANGED_TASKS` is empty, continue to step (6).
2. If not empty, do not merge yet. Inspect diffs and adapt scripts first.

Adaptation rules:
1. If `src/task/DailyTask.py` changed:
- Update `auto_daily.py`.
- Keep `apply_daily_config` aligned with upstream behavior.
2. If `src/task/TacetTask.py` changed:
- Update `auto_stamina.py`.
- Keep `apply_stamina_config` aligned with upstream behavior.
3. If `src/task/BaseCombatTask.py` changed:
- Review contract/hook changes affecting `custom/task/my_FastFarmEchoTask.py`.
- Recheck combat-loop APIs: `sleep_check_combat` vs `sleep_check`, `check_combat`, `combat_once`, `raise_not_in_combat`.
- Update `custom/task/my_FastFarmEchoTask.py` and the top-level script `auto_farm.py` if needed.
- Preserve current behavior: no noisy expected out-of-combat errors during boss death/respawn, and no fight-loop regression.

Validation before continuing:
1. Run syntax checks on touched scripts:
- `python3 -m py_compile auto_daily.py auto_stamina.py auto_farm.py custom/task/my_FastFarmEchoTask.py`
2. If adaptation confidence is low:
- Open an inbox item describing changes, attempted fixes, and why merge is unsafe.
- Stop.

---

### (6) Merge `master` into `my`

Run:

```bash
git switch my
git pull --ff-only origin my
git merge master
```

- If `git pull --ff-only origin my` fails: open an inbox item explaining local `my` diverged from `origin/my`, then stop.

### (7) If merge conflicts occur

List conflicted files:

```bash
git diff --name-only --diff-filter=U
```

Resolve with these rules:

1. Primary goal: `my` must keep `auto_daily.py`, `auto_stamina.py`, and `auto_farm.py` working.
2. Preference rules:
- Prefer `my` changes, especially intentional deletions in `config.py` and deleted files.
- Do not reintroduce removed logic unless strictly necessary.
3. If confidence is low:
- Abort merge, open an inbox item with observations and ambiguity, then stop.

---

### (8) On successful merge

Run:

```bash
git push origin my
```

Then open an inbox item summarizing:
- what changed,
- whether `DailyTask.py`, `TacetTask.py`, or `BaseCombatTask.py` changed,
- whether script adaptations were required.

---

### (9) Improve the prompt when warranted

During each run, note opportunities to make future runs safer and less manual.

Trigger if any of these occur:
1. A recurring failure mode appears (for example API drift, repeated conflict patterns, repeated command failures).
2. A manual decision could be converted into a deterministic rule.
3. A validation gap is discovered.
4. A step is consistently redundant or misordered.

If triggered:
1. Update `agents/merge_automation.md` in the same run with a minimal, concrete improvement.
2. Keep scope limited to sync/merge process clarity and safety.
3. Prefer concise rules with exact commands and explicit stop conditions.
4. Add a short inbox note with:
- the finding,
- the prompt change,
- why it improves future runs.

If not triggered:
1. Do not modify the prompt.
