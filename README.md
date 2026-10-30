# Project site

This directory contains the English, dependency-free GitHub Pages site for [iOS on Pixel 6](https://everettjf.github.io/pixel6ios/). It has no analytics, external fonts, or build step. The two JPEGs are physical-device photographs supplied by the project tester.

Preview from the repository root:

```sh
python3 -m http.server 8000 --directory web
```

After committing and pushing changes to `main`, publish them locally with:

```sh
tools/publish-github-pages.sh
```

The script pushes a subtree split of `web/` to the root of the `gh-pages` branch. GitHub Pages uses that branch as its source; no GitHub Actions build workflow is required. Site source remains reviewable under `web/` on `main`.
