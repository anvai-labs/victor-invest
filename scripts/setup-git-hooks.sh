#!/bin/bash
# Setup script for victor-invest git hooks
# Run this script to install pre-commit and commit-msg hooks

set -e

echo "Setting up victor-invest git hooks..."

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Set the hooks path
git config core.hooksPath .githooks

echo "Git hooks configured successfully!"
echo ""
echo "Installed hooks:"
echo "  - pre-commit: Runs ruff, black, and mypy checks before commit"
echo "  - commit-msg: Validates commit messages don't contain AI model co-author references"
echo ""
echo "To bypass these hooks temporarily, use:"
echo "  git commit --no-verify"
echo ""
echo "To uninstall, run:"
echo "  git config --unset core.hooksPath"
