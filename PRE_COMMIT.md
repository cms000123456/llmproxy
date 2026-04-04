# Pre-commit Hooks Guide

This document explains how to use pre-commit hooks for the LLM Proxy project.

## What are Pre-commit Hooks?

Pre-commit hooks are scripts that run automatically before each commit to catch issues before they reach CI/CD. They help maintain code quality and prevent common mistakes.

## Installation

### 1. Install pre-commit

```bash
# Using pip
pip install pre-commit

# Or using pipx (recommended)
pipx install pre-commit

# Or on macOS with Homebrew
brew install pre-commit
```

### 2. Install Git Hooks

```bash
# Navigate to the project root
cd /path/to/llmproxy

# Install the pre-commit hooks
pre-commit install

# Optional: Install pre-push hooks (runs tests before push)
pre-commit install --hook-type pre-push
```

### 3. Verify Installation

```bash
# Check that hooks are installed
pre-commit --version

# Run hooks on all files (initial setup)
pre-commit run --all-files
```

## Usage

### Automatic (Recommended)

Once installed, hooks run automatically on every commit:

```bash
git add .
git commit -m "Your commit message"
# Hooks run automatically here
```

If hooks find issues, the commit is blocked until you fix them.

### Manual Run

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff

# Run on specific file
pre-commit run --files llmproxy/server.py

# Skip hooks (not recommended)
git commit -m "message" --no-verify
```

## Available Hooks

### Code Quality

| Hook | Purpose | Fix Automatically? |
|------|---------|-------------------|
| `ruff` | Python linting and import sorting | ✅ Yes |
| `ruff-format` | Python code formatting | ✅ Yes |
| `mypy` | Static type checking | ❌ No |
| `bandit` | Security vulnerability scanning | ❌ No |

### General Files

| Hook | Purpose |
|------|---------|
| `trailing-whitespace` | Remove trailing whitespace |
| `end-of-file-fixer` | Ensure files end with newline |
| `check-yaml` | Validate YAML syntax |
| `check-json` | Validate JSON syntax |
| `check-toml` | Validate TOML syntax |
| `check-added-large-files` | Prevent committing large files (>500KB) |
| `mixed-line-ending` | Enforce LF line endings |

### Security

| Hook | Purpose |
|------|---------|
| `detect-private-key` | Detect private keys in code |
| `detect-aws-credentials` | Detect AWS credentials |
| `detect-secrets` | Scan for secrets and credentials |

### Docker & Infrastructure

| Hook | Purpose |
|------|---------|
| `hadolint-docker` | Lint Dockerfiles |
| `docker-compose-check` | Validate docker-compose files |
| `shellcheck` | Lint shell scripts |
| `actionlint` | Validate GitHub Actions workflows |

### Documentation

| Hook | Purpose | Fix Automatically? |
|------|---------|-------------------|
| `markdownlint` | Lint Markdown files | ✅ Yes |

### Tests (Pre-push)

| Hook | Purpose | Stage |
|------|---------|-------|
| `pytest-check` | Run unit tests | push |
| `check-version` | Verify version consistency | commit |

## Troubleshooting

### Hook Failures

**Ruff formatting issues:**
```bash
# Auto-fix formatting
pre-commit run ruff --all-files

# Or manually
ruff format .
ruff check --fix .
```

**Type checking failures:**
```bash
# Run mypy manually
mypy llmproxy --ignore-missing-imports
```

**Secret detection false positives:**
```bash
# Mark line as not a secret
# Add "# pragma: allowlist secret" comment
detect-secrets scan --baseline .secrets.baseline
```

### Performance

**Slow hooks:**
```bash
# Run only changed files (default)
pre-commit run

# Skip specific hook
SKIP=mypy git commit -m "message"

# Disable hooks temporarily
pre-commit uninstall
```

### CI/CD Integration

Pre-commit hooks complement CI/CD:
- **Local**: Fast feedback on common issues
- **CI**: Comprehensive checks and cross-platform testing

## Configuration

### Skipping Hooks

```bash
# Skip specific hook
SKIP=ruff git commit -m "message"

# Skip multiple hooks
SKIP=ruff,mypy git commit -m "message"

# Skip all hooks (emergency only)
git commit -m "message" --no-verify
```

### Updating Hooks

```bash
# Update all hooks to latest versions
pre-commit autoupdate

# Update specific hook
pre-commit autoupdate --repo https://github.com/astral-sh/ruff-pre-commit
```

### Custom Configuration

Edit `.pre-commit-config.yaml` to customize hooks:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        # Exclude specific files
        exclude: ^(tests/|scripts/)
```

## Best Practices

1. **Install hooks early**: Set up pre-commit when you start working on the project

2. **Don't skip hooks**: Only use `--no-verify` in emergencies

3. **Fix issues immediately**: Address hook failures before committing

4. **Keep hooks updated**: Run `pre-commit autoupdate` monthly

5. **Use with CI**: Hooks catch issues fast locally; CI catches platform-specific issues

## IDE Integration

### VS Code

Install the "Pre-commit" extension for automatic formatting on save:

```json
// settings.json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "charliermarsh.ruff",
  "ruff.importStrategy": "useBundled"
}
```

### PyCharm

Enable "Reformat code" and "Optimize imports" on save:
- Settings → Tools → Actions on Save
- Check "Reformat code" and "Optimize imports"

## Workflow Example

```bash
# 1. Make changes
vim llmproxy/server.py

# 2. Stage changes
git add llmproxy/server.py

# 3. Try to commit (hooks run automatically)
git commit -m "Add new feature"
# ❌ Hooks failed: ruff found formatting issues

# 4. Fix issues
pre-commit run ruff --all-files
# ✅ Fixed automatically

# 5. Stage fixed files
git add llmproxy/server.py

# 6. Commit again
git commit -m "Add new feature"
# ✅ Hooks passed, commit successful

# 7. Push (pre-push hooks run tests)
git push
# ✅ Tests passed, push successful
```

## Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Pre-commit Hooks List](https://pre-commit.com/hooks.html)
