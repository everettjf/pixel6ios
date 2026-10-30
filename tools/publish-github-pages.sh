#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to publish: commit or remove working-tree changes first." >&2
  exit 1
fi

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Refusing to publish: switch to main first." >&2
  exit 1
fi

if ! git diff --quiet HEAD origin/main; then
  echo "Refusing to publish: local main differs from origin/main." >&2
  exit 1
fi

for file in web/index.html web/styles.css web/.nojekyll; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required site file: $file" >&2
    exit 1
  fi
done

site_commit="$(git subtree split --prefix=web HEAD)"
git push origin "$site_commit:refs/heads/gh-pages"
echo "Published web/ from $(git rev-parse --short HEAD) to gh-pages ($site_commit)."
echo "Site: https://everettjf.github.io/pixel6ios/"
