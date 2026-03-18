#!/usr/bin/env bash
# new-city.sh — Scaffold a new urbanism guide city repo
# Usage: ./new-city.sh <city-name> <base-url> <github-repo> <timezone>
# Example: ./new-city.sh portland portland.urbanism-guide.com prestomation/portland-urbanism-guide "America/Los_Angeles"

set -euo pipefail

CITY_NAME="${1:?Usage: $0 <city-name> <base-url> <github-repo> <timezone>}"
BASE_URL="${2:?}"
GITHUB_REPO="${3:?}"
TIMEZONE="${4:-America/Los_Angeles}"
OUTPUT_DIR="${CITY_NAME}-urbanism-guide"

echo "=== Scaffolding new city: $CITY_NAME ==="
echo "Base URL: https://$BASE_URL/"
echo "GitHub repo: $GITHUB_REPO"
echo "Timezone: $TIMEZONE"
echo "Output dir: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"/{content/{glossary,guides,blog,timeline,data,quick-start},.github/workflows,static/css,data,archetypes,scripts}

# go.mod
cat > "$OUTPUT_DIR/go.mod" << EOF
module github.com/$GITHUB_REPO

go 1.21

require github.com/prestomation/urbanism-guide-core v0.3.0
EOF

# hugo.toml
cat > "$OUTPUT_DIR/hugo.toml" << EOF
baseURL = "https://$BASE_URL/"
title = "${CITY_NAME^} Urbanism Guide"

[module]
[[module.imports]]
path = "github.com/prestomation/urbanism-guide-core"

[params]
  description = "A practical guide for ${CITY_NAME^} urbanists and advocates."
  goatCounterCode = "${CITY_NAME}-urbanism-guide"
  BookRepo = "https://github.com/$GITHUB_REPO"
  BookEditPath = "edit/main/content"
EOF

# brand.css
cat > "$OUTPUT_DIR/static/css/brand.css" << 'EOF'
/* ==========================================================================
   City Urbanism Guide — Brand Colors
   Replace these values with your city's color palette.
   ========================================================================== */

:root {
  --color-link: #0046AD;
  --accent-teal: #00839A;
  --accent-emerald: #52B788;
  --accent-gold: #E9B44C;
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
EOF

# .github/workflows/deploy.yml
cat > "$OUTPUT_DIR/.github/workflows/deploy.yml" << EOF
name: Deploy

on:
  push:
    branches: ["main"]
  workflow_dispatch:

jobs:
  deploy:
    uses: prestomation/urbanism-guide-core/.github/workflows/deploy.yml@v0.3.0
    with:
      timezone: "$TIMEZONE"
    permissions:
      contents: write
EOF

# .github/workflows/pr-preview.yml
cat > "$OUTPUT_DIR/.github/workflows/pr-preview.yml" << EOF
name: PR Preview

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  preview:
    uses: prestomation/urbanism-guide-core/.github/workflows/pr-preview.yml@v0.3.0
    with:
      timezone: "$TIMEZONE"
      base_url: "https://$BASE_URL"
    permissions:
      contents: write
      pull-requests: write
EOF

# .github/workflows/pr-preview-cleanup.yml
cat > "$OUTPUT_DIR/.github/workflows/pr-preview-cleanup.yml" << EOF
name: PR Preview Cleanup

on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    uses: prestomation/urbanism-guide-core/.github/workflows/pr-preview-cleanup.yml@v0.3.0
    permissions:
      contents: write
EOF

# .htmltest.yml
cat > "$OUTPUT_DIR/.htmltest.yml" << 'EOF'
DirectoryPath: "public"
CheckInternal: true
CheckInternalHash: true
CheckExternal: false
IgnoreURLs:
  - "^mailto:"
  - "^/pr-preview/"
IgnoreDirs:
  - "^pr-preview/"
OutputDir: ".htmltest"
EOF

# static/CNAME
echo "$BASE_URL" > "$OUTPUT_DIR/static/CNAME"

# .gitignore
cat > "$OUTPUT_DIR/.gitignore" << 'EOF'
public/
resources/
.hugo_build.lock
.htmltest/
_vendor/
node_modules/
EOF

# content/_index.md
cat > "$OUTPUT_DIR/content/_index.md" << EOF
---
title: "${CITY_NAME^} Urbanism Guide"
---

# ${CITY_NAME^} Urbanism Guide

A practical reference for urbanists and advocates in **${CITY_NAME^}**.

---

{{< columns >}}

## [Quick Start]({{< relref "/quick-start" >}})

How city government works — planning commission, zoning, and how to get involved.

<--->

## [Glossary]({{< relref "/glossary" >}})

Plain-language definitions for urban planning terms.

<--->

## [Guides]({{< relref "/guides" >}})

In-depth coverage of walkability, transit, housing, and cycling.

{{< /columns >}}

{{< columns >}}

## [Timeline]({{< relref "/timeline" >}})

Key events in ${CITY_NAME^}'s urban development history.

<--->

## [Data]({{< relref "/data" >}})

Public data sources for planning, zoning, transit, and housing.

<--->

## [Blog]({{< relref "/blog" >}})

Analysis and commentary on urbanism in ${CITY_NAME^}.

{{< /columns >}}
EOF

# Stub _index.md files for each section
for section in glossary guides blog timeline data quick-start; do
  cat > "$OUTPUT_DIR/content/$section/_index.md" << EOF
---
title: "${section^}"
weight: 1
bookFlatSection: true
---

# ${section^}

_Content coming soon._
EOF
done

# Copy data examples
cp data/site_stats.yaml.example "$OUTPUT_DIR/data/site_stats.yaml.example" 2>/dev/null || true
cp data/timeline.yaml.example "$OUTPUT_DIR/data/timeline.yaml.example" 2>/dev/null || true

echo ""
echo "=== Scaffolded: $OUTPUT_DIR ==="
echo ""
echo "Next steps:"
echo "  1. cd $OUTPUT_DIR && git init && git add -A && git commit -m 'Initial scaffold'"
echo "  2. Create GitHub repo: gh repo create $GITHUB_REPO --public"
echo "  3. git remote add origin https://github.com/$GITHUB_REPO.git && git push -u origin main"
echo "  4. Edit static/css/brand.css with your city's colors"
echo "  5. Add DNS record: <subdomain>.urbanism-guide.com CNAME prestomation.github.io"
echo "  6. Enable GitHub Pages in repo Settings > Pages (source: gh-pages branch)"
echo "  7. Fill in content/_index.md and content sections"
