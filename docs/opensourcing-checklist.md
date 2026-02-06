# Open-Sourcing Checklist

## Before making the repository public

1. Confirm no secrets are tracked: `git ls-files | xargs rg -n "api_key|token|secret"`.
2. Rotate any credentials used during development (for example local `.env` values).
3. Ensure `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md` are present.
4. Verify CI is enabled in GitHub Actions and passing on `main`.
5. Enable branch protection on `main` (required reviews + required status checks).
6. Enable private vulnerability reporting and security advisories in GitHub settings.
7. Review docs for internal-only links, organization names, and unpublished endpoints.
8. Create an initial release tag and changelog entry.

## Recommended repository settings

1. Require pull request reviews for `main`.
2. Require CI status checks before merge.
3. Block force pushes and branch deletions on protected branches.
4. Enable Dependabot security updates.
