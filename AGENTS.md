# AGENTS.md — urbanism-guide-core

Agent instructions for working in this repository and creating new city sites.

## Repository Overview

`urbanism-guide-core` is a Hugo module that provides shared layouts, shortcodes, CSS, scripts, and reusable GitHub Actions workflows for the urbanism-guide platform. City-specific repos (`bothell-urbanism-guide`, `lakewood-urbanism-guide`, etc.) import this module via `go.mod` and inherit all resources.

## Architecture

```
urbanism-guide-core (this repo)
    └── provides: layouts, shortcodes, CSS, scripts, workflows

city-repo (e.g. bothell-urbanism-guide)
    ├── go.mod → requires urbanism-guide-core vX.Y.Z
    ├── hugo.toml → imports urbanism-guide-core module
    ├── content/ → all city-specific content (Markdown)
    ├── data/ → timeline.yaml, site_stats.yaml
    ├── static/css/brand.css → city color palette (overrides framework.css vars)
    └── .github/workflows/ → thin stubs calling core's reusable workflows
```

## Creating a New City

### 1. Run the scaffold script

From inside the core repo:
```bash
bash scripts/new-city.sh <city-name> <subdomain>.urbanism-guide.com prestomation/<city>-urbanism-guide "America/Timezone"
```

This generates a complete city repo structure in `./<city-name>-urbanism-guide/`.

### 2. City-specific customization

After scaffolding, the only required customizations are:

**`static/css/brand.css`** — city color palette:
```css
:root {
  --color-link: #YOUR_PRIMARY;
  --accent-teal: #YOUR_SECONDARY;
  --accent-gradient: linear-gradient(135deg, #PRIMARY, #SECONDARY);
}
@media (prefers-color-scheme: dark) { ... }
```

**`hugo.toml`** — city identity:
```toml
baseURL = "https://yourcity.urbanism-guide.com/"
title = "Your City Urbanism Guide"
[params]
  description = "..."
  goatCounterCode = "yourcity-urbanism-guide"
  BookRepo = "https://github.com/prestomation/yourcity-urbanism-guide"
```

**`content/_index.md`** — homepage intro paragraph (the card grid is scaffolded already)

**`data/timeline.yaml`** — city history entries (copy from `.example`, add entries newest-first)

**`data/site_stats.yaml`** — key city statistics used by `{{< stat >}}` shortcode

### 3. DNS and hosting setup

For GitHub Pages cities (the standard):
1. Add Route 53 CNAME: `yourcity.urbanism-guide.com → prestomation.github.io` (TTL 300)
2. Push `main` branch — first deploy creates the `gh-pages` branch
3. Go to GitHub repo Settings → Pages → set source to `gh-pages` branch, custom domain to `yourcity.urbanism-guide.com`

For Cloudflare Pages cities (like Seattle):
- No CNAME file needed — Cloudflare manages DNS
- Use `validate.yml` stub instead of `deploy.yml` (Cloudflare auto-builds)
- Set Cloudflare build command: `hugo --gc --minify && npx pagefind --site public`

### 4. Verify the deploy

After the first push to main:
```bash
bash ~/.openclaw/workspace/skills/post-pull-request/scripts/check_deploy.sh \
  prestomation/yourcity-urbanism-guide \
  --url https://yourcity.urbanism-guide.com/ \
  --timeout-minutes 15
```

## Module Versioning

When releasing a new core version:
1. Merge all changes to main
2. `git tag vX.Y.Z && git push origin vX.Y.Z`
3. The release workflow auto-creates a GitHub Release
4. Update each city's `go.mod` to reference the new version
5. Bump workflow stubs to `@vX.Y.Z`

**Semantic versioning conventions:**
- **Patch** (`vX.Y.z`): Bug fixes, CSS tweaks, script improvements
- **Minor** (`vX.y.0`): New shortcodes, new workflow features, non-breaking additions
- **Major** (`vX.0.0`): Breaking changes to layout structure or required config keys

## What Belongs in Core vs City

| Type | Core | City |
|------|------|------|
| Layouts (`baseof.html`, partials) | ✅ | Override only if needed |
| Shortcodes (`timeline`, `blog-list`, `glossary-filter`, `stat`, `columns`) | ✅ | City-specific shortcodes only |
| CSS framework (`framework.css`) | ✅ | `brand.css` colors only |
| Scripts (`validate-timeline.py`, `check-external-links.py`) | ✅ | Override if city-specific behavior needed |
| Reusable workflows | ✅ | Thin stubs only |
| Content (`content/`) | ❌ | City-owned |
| Data (`data/timeline.yaml`, `data/site_stats.yaml`) | Example files only | City-owned |
| Archetypes | ✅ defaults | Override for city-specific copy |

## Shortcode Reference

### `{{< timeline >}}`
Renders `data/timeline.yaml`. No arguments. Entries must be newest-first.

### `{{< blog-list >}}`
Lists all pages in the `blog` section, newest first. No arguments.

### `{{< glossary-filter >}}`
Renders a filter bar for glossary pages. Tags come from front matter `tags:` in each glossary entry. No arguments — reads all pages in the `glossary` section.

### `{{< stat "key.path" >}}`
Injects a value from `data/site_stats.yaml` using dot notation.
Optional `file` param to read from a different data file: `{{< stat "key" file="link_system" >}}`

### `{{< columns >}}`
Creates a flex column layout. Use `<--->` to separate columns. Markdown inside columns is rendered correctly (including `## [Title](url)` as card headings).

## CI/CD Pipeline

Each city runs three workflows:
1. **`deploy.yml`** — triggers on push to `main`, builds and deploys to `gh-pages`
2. **`pr-preview.yml`** — triggers on PR open/update, deploys preview to `gh-pages/pr-preview/N/`
3. **`pr-preview-cleanup.yml`** — triggers on PR close, removes the preview directory

All three are thin stubs calling core's reusable workflows. The core workflows handle: Hugo install, module sync, timeline validation, Hugo build, Pagefind indexing, build output validation (page count + CNAME check), link validation, and deploy.

## Known Limitations

- `go.sum` is not committed in city repos — `hugo mod tidy` runs in CI instead
- Fine-grained GitHub PAT cannot configure GitHub Pages via API — must be done manually in repo Settings
- Cloudflare Pages doesn't support the gh-pages push pattern — use `validate.yml` + Cloudflare auto-build
