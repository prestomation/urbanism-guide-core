# urbanism-guide-core

Shared Hugo module providing layouts, shortcodes, CSS framework, archetypes, build scripts, and reusable GitHub Actions workflows for the urbanism-guide platform.

City-specific repositories import this module and inherit all resources. Local files automatically override module files due to Hugo's precedence rules.

## Quick Start

### 1. City repo `go.mod`

```
module github.com/your-org/your-city-urbanism-guide

go 1.21

require github.com/prestomation/urbanism-guide-core v0.0.0
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
| **Layouts** | `baseof.html`, shortcodes (`timeline`, `blog-list`), partials (search, analytics, inject hooks) | Drop a local file at the same path |
| **CSS** | `framework.css` using CSS custom properties for all colors | Create `static/css/brand.css` or override `framework.css` entirely |
| **Archetypes** | `default.md`, `glossary.md`, `blog.md` | Place local archetypes at same path |
| **Scripts** | `validate-timeline.py`, `check-external-links.py` | Provide local scripts or disable via workflow inputs |
| **Workflows** | `deploy.yml`, `pr-preview.yml`, `pr-preview-cleanup.yml` (all `workflow_call`) | Don't call the reusable workflow; write your own |
| **Config** | Shared `hugo.toml` defaults, `.htmltest.yml` | Override any setting in city `hugo.toml` |

## Content Structure Convention

Archetypes and shortcodes assume these content paths but don't enforce them:

- `content/glossary/` -- glossary term pages
- `content/guides/` -- topic-specific guides
- `content/blog/` -- blog posts (used by `blog-list` shortcode)
- `content/timeline/` -- timeline page using `data/timeline.yaml`

All features degrade gracefully if unused.

## Versioning

City repos can pin imports to specific versions:

```
require github.com/prestomation/urbanism-guide-core v1.2.0
```

Or track `@main` for continuous updates.