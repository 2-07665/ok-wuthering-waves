#!/usr/bin/env zsh
set -euo pipefail

# Sync local master with upstream/master using fast-forward only,
# then rebase my onto master, refresh submodules, and push both branches.

if ! git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "Error: not inside a git repository."
  exit 1
fi

cd "$git_root"

start_branch="$(git branch --show-current)"

git fetch upstream --prune
git switch master
git merge --ff-only upstream/master
git push origin master
git switch my
git rebase master
git submodule update --init --recursive
git push --force-with-lease origin my

if [[ -n "$start_branch" && "$start_branch" != "my" ]]; then
  git switch "$start_branch"
fi

echo "master is synced with upstream/master, and my is rebased onto master."
