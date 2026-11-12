### Github Dumper

[![CI](https://github.com/Core2002/dump_github/actions/workflows/ci.yml/badge.svg)](https://github.com/Core2002/dump_github/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dump-github.svg)](https://pypi.org/project/dump-github/)

Github Dumper is a Python program designed to search for users' GitHub repositories and download the repositories. This tool can be used to back up users' GitHub repositories in case they need them later.

**Install (Python 3.10+):**

```
pip install -U dump-github
```

**Usage:**

```
usage: dump-github [-h] [-d] [-p] [--version] [--token TOKEN]
                   [--limit_size LIMIT_SIZE]
                   username

Backup users github repo.

positional arguments:
  username

options:
  -h, --help            show this help message and exit
  -d, --download_zip    only download zip file
  -p, --print           only print urls
  --version             show program's version number and exit
  --token TOKEN         GitHub personal access token (or set GITHUB_TOKEN).
                        Required for private repos and higher API rate limits.
  --limit_size LIMIT_SIZE
                        limit size(MB) of download zip file, if 0 then no
                        limit(default:100).

https://github.com/Core2002/dump_github
```

### Authentication (token)

GitHub’s API requires a proper `Authorization: Bearer <token>` header. This tool accepts a **personal access token** in two ways (first match wins):

1. **`--token`** on the command line  
2. **`GITHUB_TOKEN`** environment variable (if `--token` is empty)

**Why use a token?**

- **Private repositories**: Without a token, only public repos are listed and can be cloned or archived. With a token that has the right scopes, you can include private repos you are allowed to access (for example when backing up your own account).
- **Rate limits**: Authenticated API requests get a much higher limit than anonymous requests.

**Without a token**

Only public repositories can be listed and downloaded. The anonymous GitHub API allows
60 requests per hour per IP, which shared/NATed networks and CI runners exhaust quickly;
if `api.github.com` is rate-limited or otherwise unavailable, the tool automatically
falls back to the public GitHub web listing
(`github.com/{user}?tab=repositories` / `github.com/orgs/{org}/repositories`), prints a
warning and keeps going. Private repositories still require a token.

**How the token is used**

- **Listing repos**: sent as `Bearer` on the REST API and scoped strictly to the requested account:
  - **organisation** → `GET /orgs/{org}/repos?type=all` — only repositories owned by that organisation (private ones included when the token may access them);
  - **your own user account** → `GET /user/repos?affiliation=owner` — private and public repos, without organisation/collaborator repos;
  - **any other user** → `GET /users/{username}/repos?type=owner`.

  Repositories whose owner is not the requested account are discarded as a final guard, so a user dump never includes organisation repositories and an organisation dump never includes user repositories.
- **Clone** (default mode): the token is handed to `git` through a one-shot credential helper (`credential.helper` reads `DUMP_GITHUB_TOKEN` from the child process environment), so the clone URL stays `https://github.com/...`. The token is never shown in `ps` output and never written to the cloned repository's `.git/config`; existing credential helpers are reset for that clone so a stale stored credential cannot shadow the token.
- **Zip download** (`-d`): uses the [repository archive (zipball)](https://docs.github.com/en/rest/repos/repos#download-a-repository-archive-zip) API with the same `Bearer` header (via `curl`), which works for private repos; without a token, public archive URLs are used instead.

Create a token under GitHub → **Settings** → **Developer settings** → **Personal access tokens**. For private repo backup, enable access to **repository contents** (classic PAT: `repo` scope; fine-grained: read access to the repositories you need).

**Examples**

```bash
# Public repos only (no token; falls back to the web listing if the API is rate-limited)
dump-github Core2002 -p

# Public backup without any credentials
dump-github Core2002 -d

# Token on the command line (private + higher API limits)
dump-github username --token ghp_xxxxxxxxxxxx

# Back up an organisation (only that organisation's repositories)
dump-github some-org --token ghp_xxxxxxxxxxxx

# Same, via environment variable (recommended to avoid shell history)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
dump-github Core2002 -d
```

**Security note:** Do not commit tokens or paste them into shared logs. Prefer `GITHUB_TOKEN` in a local shell profile or a secret manager, and rotate the token if it leaks. Cloned repositories keep a clean remote URL (`https://github.com/...`), so `.git/config` does not contain the token.

### Development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
python -m build                  # dist/: sdist + wheel
python -m twine check dist/*
```

CI runs the test suite on Python 3.10, 3.12 and 3.13, and checks the build metadata with `twine check` (`.github/workflows/ci.yml`).

### Releasing

1. Bump `__version__` in `dump_github/_version.py` and move the changelog entries in `CHANGELOG.md` to the new version.
2. Commit, tag and push:
   ```bash
   git tag v0.2.0
   git push origin main v0.2.0
   ```
3. The `Release` workflow runs the tests, builds the sdist and wheel, checks them with `twine check` and publishes both to PyPI through **Trusted Publishing**.

One-time setup on PyPI: add a trusted publisher for the `Core2002/dump_github` repository and the `release.yml` workflow. No PyPI API token is stored in the repository. Manual fallback:

```bash
python -m build
python -m twine upload dist/*
```
