In `ok-wuthering-waves`, sync `master` to match `upstream/master`, then merge `master` into `my`, and stop for manual intervention if needed.

---

## Steps

### (1) Safety check

Run `git status --porcelain`.

* If not clean: open an inbox item listing the changes and stop.
* Do **not** stash, reset, or modify files.

### (2) Fetch upstream

Run `git fetch upstream`.

### (3) Update local master

Record the current `master` commit hash (so we can later see what changed in this sync):

```
OLD_MASTER=$(git rev-parse master)
```

Then run:

```
git switch master
git merge --ff-only upstream/master
```

* If `--ff-only` fails: open an inbox item explaining that `master` diverged from `upstream/master` and stop (do not force-reset).
* If `master` is already up to date. Stop and archive.

### (4) Update origin/master

Run `git push origin master`.

* If push fails (non-FF, auth, or other error): open an inbox item with the error and stop.

---

### (5) Pre-merge compatibility check (critical)

Before merging into `my`, check whether the updated `master` introduced changes to either of these files:

* `src/task/DailyTask.py`
* `src/task/TacetTask.py`

Use (path-limited diff for **only the commits pulled in during this sync**):

```
NEW_MASTER=$(git rev-parse master)
# If OLD_MASTER == NEW_MASTER, master was already up to date and we would have stopped earlier.
git diff --name-only "$OLD_MASTER".."$NEW_MASTER" -- src/task/DailyTask.py src/task/TacetTask.py
```

- If the command outputs **nothing**, proceed to step (6).
- If it outputs **either file**:
  - Assume the upstream changes **may break** the automated scripts `auto_daily.py` and `auto_stamina.py` (they import these files directly).
  - **Do NOT merge directly.**
  - Inspect the diffs of the changed task file(s) on `master`.
  - Update `auto_daily.py` and `auto_stamina.py` so that they conform to the new behavior. Note: In `auto_daily.py`, DailyTask is configured through the method `apply_daily_config`. In `auto_stamina.py`, TacetTask is configured through the method `apply_stamina_config`.
  - Ensure the scripts still run correctly.
  - If you cannot confidently adapt the scripts: open an inbox item explaining what changed and why it is unsafe to proceed, then stop.

---

### (6) Merge into `my`
Run:
```

git switch my
git pull --ff-only origin my
git merge master

```

* If `git pull --ff-only origin my` fails: open an inbox item explaining that local `my` diverged from `origin/my` and stop.

### (7) If merge reports conflicts
Collect conflicted files via:
```

git diff --name-only --diff-filter=U

```

Resolve conflicts according to the following rules:

1. **Primary goal**:
   The branch `my` exists to run the custom automated scripts `auto_daily.py` and `auto_stamina.py`.

   I only intentionally modified:
   - `config.py`
   - `src/task/BaseWWTask.py` (the `use_stamina` method)
   - `src/task/TacetTask.py` (to use the custom `use_stamina` behavior)

   All other files in `src/` should match `master`.
   Custom code under `custom/` should not be affected during the merge. They are not present in the upstream reposity.

   Your **top priority** is ensuring that `auto_daily.py` and `auto_stamina.py` continue to run correctly as they do now.

2. **Preference rules**:
   - Prefer changes in `my`, especially:
     - Deleted lines in `config.py`
     - Deleted files
   - Avoid re-introducing removed logic unless strictly required.

3. If you cannot resolve a conflict with high confidence, abort the merge, open an inbox item explaining what you observed and why the decision is unclear, then stop.

---

### (8) Successful merge
If the merge succeeds, push it to origin with:
```

git push origin my

```

Then open an inbox item summarizing:
- What changed
- Whether `DailyTask.py` or `TacetTask.py` were involved
- Whether any script adaptations were required
