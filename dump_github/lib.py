import re
import warnings
from urllib.parse import quote

import requests

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"
PER_PAGE = 100
WEB_USER_AGENT = "dump-github (+https://github.com/Core2002/dump_github)"


class GitHubAPIError(RuntimeError):
    """GitHub could not be read through the REST API (or the web fallback)."""

    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _github_auth_headers(token):
    """GitHub REST API expects Authorization: Bearer <token> (PAT classic / fine-grained)."""
    if not token:
        return {}
    token = token.strip()
    if not token:
        return {}
    if token.lower().startswith(("bearer ", "token ", "basic ")):
        return {"Authorization": token}
    return {"Authorization": "Bearer {}".format(token)}


def _api_headers(token=""):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    headers.update(_github_auth_headers(token))
    return headers


def _api_get(path, token=""):
    """GET one GitHub REST API path and return the decoded JSON.

    Raises GitHubAPIError instead of silently returning an empty result, so
    callers can distinguish "no repositories" from "request failed".
    """
    try:
        response = requests.get(
            GITHUB_API + path, headers=_api_headers(token), timeout=30
        )
    except requests.RequestException as exc:
        raise GitHubAPIError(None, "request failed: {}".format(exc)) from exc
    if response.status_code != 200:
        message = "HTTP {}".format(response.status_code)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("message"):
            message = "{} (HTTP {})".format(payload["message"], response.status_code)
        raise GitHubAPIError(response.status_code, message)
    try:
        return response.json()
    except ValueError as exc:
        raise GitHubAPIError(
            response.status_code, "invalid JSON response from GitHub"
        ) from exc


def get_authenticated_login(token=""):
    """Return the login of the token owner, or None if there is no usable token."""
    if not _github_auth_headers(token):
        return None
    try:
        account = _api_get("/user", token)
    except GitHubAPIError:
        return None
    if not isinstance(account, dict):
        return None
    return account.get("login") or None


def get_account_type(username, token=""):
    """Return ``"Organization"``/``"User"`` for ``username``, or None if unknown."""
    quoted = quote(username, safe="")
    try:
        account = _api_get("/users/{}".format(quoted), token)
    except GitHubAPIError:
        account = None
    if isinstance(account, dict) and account.get("type"):
        return account["type"]
    # ``/users/{org}`` is not guaranteed to resolve for organisations, so fall
    # back to the org endpoint, which unambiguously identifies one.
    try:
        org = _api_get("/orgs/{}".format(quoted), token)
    except GitHubAPIError:
        org = None
    if isinstance(org, dict) and org.get("login"):
        return "Organization"
    return None


def _repos_path(username, page, authenticated_login, account_type):
    """Build a listing API path that only contains repositories owned by ``username``.

    ``GET /user/repos`` (used by an earlier version whenever a token was
    supplied) lists every repository the token owner can see, which includes
    repositories of the organisations the token owner is a member of, and it
    ignores ``username`` entirely.  Listing must therefore be scoped to the
    requested account:

    * organisation -> ``/orgs/{org}/repos?type=all``; only repositories owned
      by that organisation, including private ones the token may access
    * own user account -> ``/user/repos?affiliation=owner``; keeps private
      repos, drops organisation/collaborator repos
    * any other user account -> ``/users/{username}/repos?type=owner``
    """
    quoted = quote(username, safe="")
    if (account_type or "").lower() == "organization":
        return "/orgs/{}/repos?type=all&per_page={}&page={}".format(
            quoted, PER_PAGE, page
        )
    own_account = bool(authenticated_login) and (
        authenticated_login.lower() == username.lower()
    )
    if own_account:
        return "/user/repos?affiliation=owner&per_page={}&page={}".format(
            PER_PAGE, page
        )
    return "/users/{}/repos?type=owner&per_page={}&page={}".format(
        quoted, PER_PAGE, page
    )


def _is_owned_by(repo, username):
    owner = repo.get("owner") or {}
    login = owner.get("login") or ""
    if login:
        return login.lower() == username.lower()
    full_name = repo.get("full_name") or ""
    return full_name.split("/", 1)[0].lower() == username.lower()


def _fetch_repos_page(username, page, token="", authenticated_login=None,
                      account_type=None):
    """Fetch one raw page of repositories owned by ``username``."""
    path = _repos_path(username, page, authenticated_login, account_type)
    repos = _api_get(path, token)
    if not isinstance(repos, list):
        return []
    return [repo for repo in repos if isinstance(repo, dict)]


def get_page_of_repos(username, page, token="", authenticated_login=None,
                      account_type=None):
    username = username.strip()
    if account_type is None:
        account_type = get_account_type(username, token)
    if authenticated_login is None:
        authenticated_login = get_authenticated_login(token)
    repos = _fetch_repos_page(
        username, page, token, authenticated_login, account_type
    )
    return [repo for repo in repos if _is_owned_by(repo, username)]


# --- public web fallback -------------------------------------------------
#
# api.github.com allows only 60 unauthenticated requests per hour *per IP*.
# Shared/NATed networks and CI runners exhaust that quickly, which used to make
# ``dump-github user`` silently return nothing.  github.com's repository pages
# are not subject to that API quota, so they are used as a read-only fallback
# for public repositories when no token is configured.

_USER_REPO_TAG_RE = re.compile(r'<a\b[^>]*itemprop="name codeRepository"[^>]*>')
_WEB_REPO_HREF_RE = re.compile(r'href="/([^"/]+)/([^"/?#]+)"')
_WEB_NEXT_RE = re.compile(r'rel="next"')
_WEB_NON_REPO_PATHS = {
    "followers",
    "following",
    "people",
    "packages",
    "projects",
    "repositories",
    "settings",
    "sponsoring",
}


def _web_get(url):
    try:
        response = requests.get(
            url, headers={"User-Agent": WEB_USER_AGENT}, timeout=30
        )
    except requests.RequestException as exc:
        raise GitHubAPIError(None, "web request failed: {}".format(exc)) from exc
    if response.status_code != 200:
        raise GitHubAPIError(
            response.status_code,
            "github.com returned HTTP {}".format(response.status_code),
        )
    return response.text


def _web_repo(owner, name):
    return {
        "name": name,
        "full_name": "{}/{}".format(owner, name),
        "owner": {"login": owner},
        "clone_url": "{}/{}/{}.git".format(GITHUB_WEB, owner, name),
        # The default branch is not exposed by the web listing; zip downloads
        # then use the HEAD archive instead.
    }


def _parse_user_repos_page(html, username):
    repos = []
    seen = set()
    for tag in _USER_REPO_TAG_RE.findall(html):
        match = _WEB_REPO_HREF_RE.search(tag)
        if not match:
            continue
        owner, name = match.group(1), match.group(2)
        if owner.lower() != username.lower() or name in seen:
            continue
        seen.add(name)
        repos.append(_web_repo(owner, name))
    return repos


def _parse_org_repos_page(html, org):
    repos = []
    seen = set()
    for owner, name in _WEB_REPO_HREF_RE.findall(html):
        if owner.lower() != org.lower():
            continue
        if name.lower() in _WEB_NON_REPO_PATHS or name in seen:
            continue
        seen.add(name)
        repos.append(_web_repo(owner, name))
    return repos


def _web_page_url(username, page, is_org):
    quoted = quote(username, safe="")
    if is_org:
        return "{}/orgs/{}/repositories?page={}".format(GITHUB_WEB, quoted, page)
    return "{}/{}?tab=repositories&page={}".format(GITHUB_WEB, quoted, page)


def _parse_web_page(html, username, is_org):
    if is_org:
        return _parse_org_repos_page(html, username)
    return _parse_user_repos_page(html, username)


def _search_via_web(username, account_type):
    """List public repositories from github.com when the REST API is unavailable."""
    is_org = (account_type or "").lower() == "organization"
    first = _web_get(_web_page_url(username, 1, is_org))
    repos = _parse_web_page(first, username, is_org)
    if not repos and account_type is None:
        # The account may be an organisation: its profile page redirects to
        # github.com/{org} and does not contain the plain repository list.
        try:
            org_first = _web_get(_web_page_url(username, 1, True))
        except GitHubAPIError as exc:
            if exc.status_code == 404:
                return []
            raise
        org_repos = _parse_org_repos_page(org_first, username)
        if not org_repos:
            return []
        is_org = True
        repos = org_repos
        first = org_first
    if not repos:
        return []
    page = 1
    while _WEB_NEXT_RE.search(first):
        page += 1
        html = _web_get(_web_page_url(username, page, is_org))
        page_repos = _parse_web_page(html, username, is_org)
        if not page_repos:
            break
        repos.extend(page_repos)
        first = html
    return repos


def _search_via_api(username, token, authenticated_login, account_type):
    page = 0
    res_repos = []
    while True:
        page += 1
        repos = _fetch_repos_page(
            username, page, token, authenticated_login, account_type
        )
        if len(repos) == 0:
            break
        res_repos += repos
        if len(repos) < PER_PAGE:
            break
    return res_repos


def search_user_repos(username, token=""):
    username = username.strip()
    authenticated_login = get_authenticated_login(token)
    account_type = get_account_type(username, token)
    try:
        repos = _search_via_api(
            username, token, authenticated_login, account_type
        )
    except GitHubAPIError as exc:
        if token or exc.status_code == 404:
            raise
        warnings.warn(
            "GitHub API request failed ({}); falling back to the public GitHub "
            "web listing. Only public repositories can be listed without a "
            "token.".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        repos = _search_via_web(username, account_type)

    # Never return repositories that belong to somebody else (e.g. a user repo
    # returned for an organisation, or an organisation the token owner is in).
    result = []
    seen = set()
    for repo in repos:
        if not _is_owned_by(repo, username):
            continue
        key = (repo.get("full_name") or repo.get("name") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(repo)
    return result


# Backward-compatible alias for the historical typo
serach_user_repos = search_user_repos
