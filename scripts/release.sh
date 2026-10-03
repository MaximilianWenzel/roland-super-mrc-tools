#!/usr/bin/env bash
# ==============================================================================
# Git-Flow Release Automation for roland-super-mrc-tools
# ==============================================================================
# Usage:
#   ./scripts/release.sh [version]
#
# Examples:
#   ./scripts/release.sh 1.0.0
#   ./scripts/release.sh 1.0.1
# ==============================================================================

set -euo pipefail

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info() {
    echo -e "${CYAN}${BOLD}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}${BOLD}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}${BOLD}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}${BOLD}[ERROR]${NC} $1" >&2
    exit 1
}

# Check git and poetry prerequisites
command -v git >/dev/null 2>&1 || error "git is required but not installed."
command -v poetry >/dev/null 2>&1 || error "poetry is required but not installed."

# Parse version argument
if [ $# -ge 1 ]; then
    VERSION_INPUT="$1"
else
    CURRENT_VER=$(poetry version -s 2>/dev/null || echo "1.0.0")
    echo -e "${CYAN}Current version:${NC} ${BOLD}${CURRENT_VER}${NC}"
    read -rp "Enter target release version (e.g. 1.0.0): " VERSION_INPUT
fi

# Strip optional leading 'v'
VERSION="${VERSION_INPUT#v}"

# Validate semantic version format (X.Y.Z)
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    error "Invalid semantic version format: '$VERSION'. Expected X.Y.Z (e.g. 1.0.0)."
fi

TAG="v$VERSION"
RELEASE_BRANCH="release/$TAG"

info "Preparing release ${BOLD}$TAG${NC}..."

# Check working directory status
if [ -n "$(git status --porcelain)" ]; then
    error "Working directory has uncommitted changes. Please commit or stash them first."
fi

# Ensure we have both main and develop branches
if ! git rev-parse --verify main >/dev/null 2>&1; then
    error "Branch 'main' does not exist."
fi

if ! git rev-parse --verify develop >/dev/null 2>&1; then
    error "Branch 'develop' does not exist. Create it first with: git checkout -b develop"
fi

# Check out develop branch
info "Switching to 'develop' branch..."
git checkout develop

# Run pre-release quality checks
info "Running test suite (pytest)..."
poetry run pytest

info "Running static type checking (mypy)..."
poetry run mypy src tests

info "Running linter and formatting checks (ruff)..."
poetry run ruff check src tests
poetry run ruff format --check src tests

success "All quality gates passed!"

# Create release branch from develop
info "Creating branch ${BOLD}$RELEASE_BRANCH${NC} from develop..."
git checkout -b "$RELEASE_BRANCH" develop

# Bump version in pyproject.toml and __init__.py
info "Bumping version to ${BOLD}$VERSION${NC}..."
poetry version "$VERSION"

poetry run python -c "
from pathlib import Path
import re

init_file = Path('src/roland_super_mrc/__init__.py')
if init_file.is_file():
    text = init_file.read_text(encoding='utf-8')
    new_text = re.sub(r'__version__\s*=\s*\"[^\"]+\"', f'__version__ = \"$VERSION\"', text)
    init_file.write_text(new_text, encoding='utf-8')
"

# Commit version bump if there are changes
if [ -n "$(git status --porcelain)" ]; then
    git add pyproject.toml src/roland_super_mrc/__init__.py
    if [ -f poetry.lock ]; then
        git add poetry.lock
    fi
    git commit -m "chore(release): bump version to $TAG"
    success "Committed version bump."
fi

# Merge release branch into main
info "Merging ${BOLD}$RELEASE_BRANCH${NC} into ${BOLD}main${NC}..."
git checkout main
git merge --no-ff "$RELEASE_BRANCH" -m "chore(release): merge $RELEASE_BRANCH into main"

# Tag main
if git rev-parse "$TAG" >/dev/null 2>&1; then
    warn "Tag $TAG already exists."
else
    info "Creating annotated git tag ${BOLD}$TAG${NC} on main..."
    git tag -a "$TAG" -m "Release $TAG"
    success "Created tag $TAG."
fi

# Merge back into develop
info "Merging ${BOLD}$RELEASE_BRANCH${NC} back into ${BOLD}develop${NC}..."
git checkout develop
git merge --no-ff "$RELEASE_BRANCH" -m "chore(release): merge $RELEASE_BRANCH into develop"

# Delete release branch
info "Cleaning up temporary ${BOLD}$RELEASE_BRANCH${NC} branch..."
git branch -d "$RELEASE_BRANCH"

success "Git-flow release for ${BOLD}$TAG${NC} completed locally!"

# Prompt to push
echo ""
echo -e "${CYAN}${BOLD}Next step:${NC} Push to remote repository to trigger GitHub Actions release builds:"
echo -e "  ${BOLD}git push origin main develop --tags${NC}"
echo ""

read -rp "Do you want to push to origin now? [y/N]: " CONFIRM_PUSH
if [[ "$CONFIRM_PUSH" =~ ^[Yy]$ ]]; then
    info "Pushing main, develop, and tags to origin..."
    git push origin main develop --tags
    success "Pushed to origin! GitHub Actions will now build multi-platform release binaries."
else
    info "Push skipped. When you are ready, run:"
    echo -e "  ${BOLD}git push origin main develop --tags${NC}"
fi
