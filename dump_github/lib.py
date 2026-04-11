import requests


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


def get_page_of_repos(username, page, token=""):
    token_header = _github_auth_headers(token)

    if token_header:
        url = "https://api.github.com/user/repos?per_page=100&page={}".format(page)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        headers.update(token_header)
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            repos = response.json()
            return repos
        else:
            return []
    else:
        url = "https://api.github.com/users/{}/repos?per_page=100&page={}".format(
            username, page
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            repos = response.json()
            return repos
        else:
            return []


def search_user_repos(username, token=""):
    page = 0
    res_repos = []

    while True:
        page += 1
        repos = get_page_of_repos(username, page, token)
        if len(repos) == 0:
            break
        res_repos += repos

    return res_repos


# Backward-compatible alias for the historical typo
serach_user_repos = search_user_repos
