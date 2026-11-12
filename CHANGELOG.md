# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-11-12

### Fixed

- Non-token mode silently returned no repositories when the anonymous GitHub API
  hit its 60 requests/hour/IP rate limit (common on shared/NAT/CI networks).
  Listing now falls back to the public GitHub web repository pages
  (`github.com/{user}?tab=repositories`, `github.com/orgs/{org}/repositories`)
  and prints a warning, so public backups work again.
- GitHub API failures are no longer swallowed: the CLI reports the error and
  exits with status 1 instead of exiting 0 with no output.
- Zip downloads no longer assume `main` when the default branch is unknown
  (web fallback); the `HEAD` archive is used, and token mode omits the ref so
  GitHub resolves the default branch.

### Tests

- 27 tests, including the API rate-limit fallback, pagination, organisation
  detection via the web listing, and the `HEAD` archive path.

## [0.2.0] - 2026-11-12

### Added

- Organisation support: `dump-github <org>` lists only repositories owned by
  that organisation, through `GET /orgs/{org}/repos`.
- `--version` flag.
- Modern packaging: PEP 621 `pyproject.toml`, sdist **and** wheel builds,
  `requires-python >= 3.10`, project URLs and PEP 639 license metadata.
- CI workflow (tests on Python 3.9/3.12/3.13) and a tag-triggered PyPI release
  workflow using Trusted Publishing.

### Fixed

- Token mode listed `GET /user/repos`, which returned the token owner's
  personal repositories plus the repositories of every organisation the token
  owner belongs to, and ignored the requested username. Listing is now scoped
  to the requested account (user or organisation) and filters out repositories
  owned by anybody else.
- Zip archive URLs now use the repository's real `full_name` instead of the
  positional username, so archives are always downloaded from the correct
  owner.
- Clone no longer embeds the token in the remote URL. A one-shot credential
  helper supplies it through the child process environment, so the token is
  not written to `.git/config` and does not show up in `ps` output.
- Removed the accidental `argparse` runtime dependency (it is a standard
  library module).

### Tests

- 15 unit and integration tests covering listing scopes, organisation
  handling, pagination, foreign-owner filtering and the git credential helper.
