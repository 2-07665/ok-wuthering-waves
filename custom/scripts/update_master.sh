set -euo pipefail

# Sync local master with upstream/master using fast-forward only,
# then rebase my onto master, refresh submodules, and push both branches.

if ! git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "Error: not inside a git repository."
  exit 1
fi

cd "$git_root"

print_section() {
  printf '\n========== %s ==========\n' "$1"
}

start_branch="$(git branch --show-current)"

print_section "Fetch upstream"
git fetch upstream --prune

print_section "Sync master"
git switch master
git merge --ff-only upstream/master
git push origin master

print_section "Rebase my onto master"
git switch my
git rebase master

print_section "Push my"
git push --force-with-lease origin my

if [[ -n "$start_branch" && "$start_branch" != "my" ]]; then
  print_section "Restore branch $start_branch"
  git switch "$start_branch"
fi

print_section "Done"
echo "master is synced with upstream/master, and my is rebased onto master."
