from urllib.parse import quote

import requests

GITHUB_API = "https://api.github.com"
PER_PAGE = 100


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
    """GET one GitHub REST API path and return the decoded JSON, or None on failure."""
    try:
        response = requests.get(
            GITHUB_API + path, headers=_api_headers(token), timeout=30
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def get_authenticated_login(token=""):
    """Return the login of the token owner, or None if there is no usable token."""
    if not _github_auth_headers(token):
        return None
    account = _api_get("/user", token)
    if not isinstance(account, dict):
        return None
    return account.get("login") or None


def get_account_type(username, token=""):
    """Return ``"Organization"``/``"User"`` for ``username``, or None if unknown."""
    quoted = quote(username, safe="")
    account = _api_get("/users/{}".format(quoted), token)
    if isinstance(account, dict) and account.get("type"):
        return account["type"]
    # ``/users/{org}`` is not guaranteed to resolve for organisations, so fall
    # back to the org endpoint, which unambiguously identifies one.
    org = _api_get("/orgs/{}".format(quoted), token)
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


def search_user_repos(username, token=""):
    username = username.strip()
    authenticated_login = get_authenticated_login(token)
    account_type = get_account_type(username, token)
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

    # Never return repositories that belong to somebody else (e.g. a user repo
    # returned for an organisation, or an organisation the token owner is in).
    return [repo for repo in res_repos if _is_owned_by(repo, username)]


# Backward-compatible alias for the historical typo
serach_user_repos = search_user_repos
