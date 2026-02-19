#!/usr/bin/env bash
set -euo pipefail

# Sync local master with upstream/master using fast-forward only,
# then push master to origin.

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

if [[ -n "$start_branch" && "$start_branch" != "master" ]]; then
  git switch "$start_branch"
fi

echo "master is synced with upstream/master."
