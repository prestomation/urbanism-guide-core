# urbanism-guide-core

Shared Hugo module providing layouts, shortcodes, CSS framework, archetypes, build scripts, and reusable GitHub Actions workflows for the urbanism-guide platform.

City-specific repositories import this module and inherit all resources. Local files automatically override module files due to Hugo's precedence rules.

## Quick Start

### 1. City repo `go.mod`

```
module github.com/your-org/your-city-urbanism-guide

go 1.21

require github.com/prestomation/urbanism-guide-core v0.2.0
```

### 2. City repo `hugo.toml`

```toml
baseURL = "https://yourcity.urbanism-guide.com/"
title = "Your City Urbanism Guide"

[module]
[[module.imports]]
path = "github.com/prestomation/urbanism-guide-core"

[params]
  description = "A practical guide for your city's urbanists."
  goatCounterCode = "your-goatcounter-code"
  BookRepo = "https://github.com/your-org/your-city-urbanism-guide"
  BookEditPath = "edit/main/content"
```

### 3. City repo `static/css/brand.css`

Override CSS custom properties to match your city's branding:

```css
:root {
  --color-link: #0046AD;
  --accent-teal: #00839A;
  --accent-emerald: #A3D559;
  --accent-gold: #FECB00;
  --accent-light-blue: #63B1E5;
  --accent-gradient: linear-gradient(135deg, #0046AD, #00839A);
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-link: #63B1E5;
    --accent-teal: #2CC8D9;
    --accent-gradient: linear-gradient(135deg, #3D7FCC, #2DAABB);
  }
}
```

### 4. City repo workflows

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: ["main"]
jobs:
  deploy:
    uses: prestomation/urbanism-guide-core/.github/workflows/deploy.yml@main
    with:
      timezone: "America/Los_Angeles"
```

```yaml
# .github/workflows/pr-preview.yml
name: PR Preview
on:
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  preview:
    uses: prestomation/urbanism-guide-core/.github/workflows/pr-preview.yml@main
    with:
      base_url: "https://yourcity.urbanism-guide.com"
```

```yaml
# .github/workflows/pr-preview-cleanup.yml
name: PR Preview Cleanup
on:
  pull_request:
    types: [closed]
jobs:
  cleanup:
    uses: prestomation/urbanism-guide-core/.github/workflows/pr-preview-cleanup.yml@main
```

## What's Included

| Layer | Contents | Override |
|-------|----------|----------|
| **Layouts** | `baseof.html`, shortcodes (`timeline`, `blog-list`, `glossary-filter`, `stat`), partials (search, analytics, inject hooks) | Drop a local file at the same path |
| **CSS** | `framework.css` using CSS custom properties for all colors | Create `static/css/brand.css` or override `framework.css` entirely |
| **Archetypes** | `default.md`, `glossary.md`, `blog.md` | Place local archetypes at same path |
| **Scripts** | `validate-timeline.py`, `check-external-links.py`, `content-metrics.py` | Provide local scripts or disable via workflow inputs |
| **Workflows** | `deploy.yml`, `pr-preview.yml`, `pr-preview-cleanup.yml`, `validate.yml` (all `workflow_call`) | Don't call the reusable workflow; write your own |
| **Config** | Shared `hugo.toml` defaults, `.htmltest.yml` | Override any setting in city `hugo.toml` |

## Shortcodes

### `glossary-filter`

Renders an interactive filter bar for glossary pages. Filters visible glossary terms by `data-tag` attribute. Requires glossary terms to be wrapped in `<div class="glossary-term" data-tag="...">`.

Supported tag values: `federal`, `state`, `county`, `city`, `concept`, `infrastructure`.

```markdown
{{</* glossary-filter */>}}

<div class="glossary-term" data-tag="city">

## Zoning
...

</div>
```

The shortcode automatically injects badge labels next to each term heading and handles keyboard navigation between filter buttons.

### `stat`

Injects a value from `data/site_stats.yaml` using dot notation. Useful for keeping time-sensitive numbers up to date in one place.

```markdown
The city has {{</* stat "housing.units_permitted_2024" */>}} permitted housing units.
```

Your city repo must provide `data/site_stats.yaml` with the appropriate keys.

## Scripts

### `content-metrics.py`

Prints content counts for a site repo. Run from the repo root:

```bash
python3 scripts/content-metrics.py
# or for machine-readable output:
python3 scripts/content-metrics.py --json
```

Reports: guide count, glossary term count (by category), timeline entries, blog posts, total word count, paragraph count, and unique external links.

## Validate Workflow

The `validate.yml` reusable workflow builds the site and optionally validates the timeline and links. Use this for city repos that need CI validation on pull requests but do not use GitHub Pages (or want a separate validate step).

```yaml
# .github/workflows/validate.yml
name: Validate
on:
  pull_request:
    branches: ["main"]
jobs:
  validate:
    uses: prestomation/urbanism-guide-core/.github/workflows/validate.yml@main
    with:
      timezone: "America/Chicago"
      run_timeline_validation: true
      run_link_validation: false
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `timezone` | `America/Los_Angeles` | TZ for Hugo build |
| `hugo_version` | `0.147.0` | Hugo version to install |
| `core_version` | `v0.2.0` | Core tag to fetch fallback `validate-timeline.py` from (pinned to prevent supply-chain risk) |
| `run_timeline_validation` | `true` | Run `validate-timeline.py` if present |
| `run_link_validation` | `true` | Run `htmltest` link checker |

## Content Structure Convention

Archetypes and shortcodes assume these content paths but don't enforce them:

- `content/glossary/` -- glossary term pages
- `content/guides/` -- topic-specific guides
- `content/blog/` -- blog posts (used by `blog-list` shortcode)
- `content/timeline/` -- timeline page using `data/timeline.yaml`

All features degrade gracefully if unused.

## Versioning

City repos should pin to a specific release tag rather than tracking `@main`:

```
require github.com/prestomation/urbanism-guide-core v0.2.0
```

**To update to a new core version:**
1. Change the version in the city repo's `go.mod`
2. Run `hugo mod tidy` to update `go.sum`
3. Test locally, then open a PR

See all releases: https://github.com/prestomation/urbanism-guide-core/releases

## Release Process (maintainers)

Releases are created by pushing a semver tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

The [release workflow](.github/workflows/release.yml) will automatically create a GitHub Release with generated release notes from commit messages since the last tag.

**Version conventions:**
- **Patch** (`v0.1.x`): CSS tweaks, bug fixes, script improvements
- **Minor** (`v0.x.0`): New layouts, shortcodes, or workflow features
- **Major** (`vX.0.0`): Breaking changes to layout structure or required config keys