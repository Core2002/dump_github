import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dump_github import lib


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def make_repo(owner, name):
    return {
        "name": name,
        "full_name": "{}/{}".format(owner, name),
        "owner": {"login": owner},
        "clone_url": "https://github.com/{}/{}.git".format(owner, name),
    }


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    @staticmethod
    def _matches(url, prefix):
        return (
            url == prefix
            or url.startswith(prefix + "?")
            or url.startswith(prefix + "/")
        )

    def route(self, routes):
        """requests.get replacement: records calls, matches exact URL or prefix."""

        def fake_get(url, headers=None, timeout=None):
            self.calls.append((url, headers or {}))
            for prefix, payload in routes:
                if self._matches(url, prefix):
                    return FakeResponse(200, payload)
            return FakeResponse(404, {"message": "Not Found"})

        return fake_get

    def urls(self):
        return [url for url, _ in self.calls]

    def repos_calls(self):
        return [(url, headers) for url, headers in self.calls if "/repos?" in url]

    def test_token_own_account_lists_only_owned_repos(self):
        routes = [
            ("https://api.github.com/user/repos", [
                make_repo("alice", "private-project"),
                make_repo("acme-org", "org-project"),  # must never leak through
            ]),
            ("https://api.github.com/users/alice",
             {"login": "alice", "type": "User"}),
            ("https://api.github.com/user", {"login": "alice"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("alice", token="ghp_test")

        self.assertEqual([repo["name"] for repo in repos], ["private-project"])
        self.assertFalse(any("/users/alice/repos" in url for url in self.urls()))
        own = [url for url in self.urls() if "/user/repos" in url]
        self.assertEqual(len(own), 1)
        self.assertIn("affiliation=owner", own[0])
        self.assertTrue(
            all(
                headers.get("Authorization") == "Bearer ghp_test"
                for _, headers in self.calls
            )
        )

    def test_token_for_another_user_uses_username_endpoint(self):
        routes = [
            ("https://api.github.com/users/alice/repos", [
                make_repo("alice", "alice-repo"),
                make_repo("acme-org", "org-project"),
            ]),
            ("https://api.github.com/users/alice",
             {"login": "alice", "type": "User"}),
            ("https://api.github.com/user", {"login": "bob"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("alice", token="ghp_test")

        self.assertEqual([repo["name"] for repo in repos], ["alice-repo"])
        self.assertIn(
            "https://api.github.com/users/alice/repos?type=owner&per_page=100&page=1",
            self.urls(),
        )
        self.assertFalse(any("/user/repos" in url for url in self.urls()))
        repos_calls = self.repos_calls()
        self.assertEqual(len(repos_calls), 1)
        self.assertEqual(
            repos_calls[0][1]["Authorization"], "Bearer ghp_test"
        )

    def test_no_token_uses_public_user_endpoint_without_auth(self):
        routes = [
            ("https://api.github.com/users/alice/repos", [
                make_repo("alice", "alice-repo"),
            ]),
            ("https://api.github.com/users/alice",
             {"login": "alice", "type": "User"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("alice")

        self.assertEqual([repo["name"] for repo in repos], ["alice-repo"])
        self.assertEqual(
            self.urls(),
            [
                "https://api.github.com/users/alice",
                "https://api.github.com/users/alice/repos?type=owner&per_page=100&page=1",
            ],
        )
        self.assertTrue(
            all("Authorization" not in headers for _, headers in self.calls)
        )

    def test_pagination_stops_on_short_page_and_resolves_once(self):
        first_page = [make_repo("alice", "repo-{}".format(i)) for i in range(100)]
        routes = [
            ("https://api.github.com/user/repos?affiliation=owner&per_page=100&page=1",
             first_page),
            ("https://api.github.com/user/repos?affiliation=owner&per_page=100&page=2",
             [make_repo("alice", "last-repo")]),
            ("https://api.github.com/users/alice",
             {"login": "alice", "type": "User"}),
            ("https://api.github.com/user", {"login": "alice"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("alice", token="ghp_test")

        self.assertEqual(len(repos), 101)
        self.assertEqual(sum(1 for url in self.urls() if url.endswith("/user")), 1)
        self.assertEqual(
            sum(1 for url in self.urls() if url.endswith("/users/alice")), 1
        )
        self.assertFalse(any("page=3" in url for url in self.urls()))

    def test_username_is_url_quoted(self):
        routes = [
            ("https://api.github.com/users/some%20user/repos", []),
            ("https://api.github.com/users/some%20user",
             {"login": "some user", "type": "User"}),
        ]

        with mock.patch.object(lib.requests, "get", self.route(routes)):
            lib.get_page_of_repos("some user", 1)

        self.assertEqual(
            self.urls()[0], "https://api.github.com/users/some%20user"
        )
        self.assertIn(
            "https://api.github.com/users/some%20user/repos", self.urls()[1]
        )

    def test_page_of_repos_filters_foreign_owners(self):
        routes = [
            ("https://api.github.com/users/alice/repos", [
                make_repo("alice", "mine"),
                make_repo("acme-org", "not-mine"),
            ]),
            ("https://api.github.com/users/alice",
             {"login": "alice", "type": "User"}),
            ("https://api.github.com/user", {"login": "bob"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.get_page_of_repos("alice", 1, token="ghp_test")

        self.assertEqual([repo["name"] for repo in repos], ["mine"])

    def test_organization_with_token_uses_org_endpoint_and_filters(self):
        routes = [
            ("https://api.github.com/orgs/acme-org/repos", [
                make_repo("acme-org", "org-private"),
                make_repo("alice", "alice-personal"),  # must never leak through
            ]),
            ("https://api.github.com/users/acme-org",
             {"login": "acme-org", "type": "Organization"}),
            ("https://api.github.com/user", {"login": "alice"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("acme-org", token="ghp_test")

        self.assertEqual([repo["name"] for repo in repos], ["org-private"])
        self.assertIn(
            "https://api.github.com/orgs/acme-org/repos?type=all&per_page=100&page=1",
            self.urls(),
        )
        self.assertFalse(any("/users/acme-org/repos" in url for url in self.urls()))
        self.assertFalse(any("/user/repos" in url for url in self.urls()))
        repos_calls = self.repos_calls()
        self.assertEqual(len(repos_calls), 1)
        self.assertEqual(
            repos_calls[0][1]["Authorization"], "Bearer ghp_test"
        )

    def test_organization_without_token_uses_org_endpoint(self):
        routes = [
            ("https://api.github.com/orgs/acme-org/repos", [
                make_repo("acme-org", "org-public"),
            ]),
            ("https://api.github.com/users/acme-org",
             {"login": "acme-org", "type": "Organization"}),
        ]
        with mock.patch.object(lib.requests, "get", self.route(routes)):
            repos = lib.search_user_repos("acme-org")

        self.assertEqual([repo["name"] for repo in repos], ["org-public"])
        self.assertEqual(
            self.urls(),
            [
                "https://api.github.com/users/acme-org",
                "https://api.github.com/orgs/acme-org/repos?type=all&per_page=100&page=1",
            ],
        )
        self.assertTrue(
            all("Authorization" not in headers for _, headers in self.calls)
        )

    def test_organization_detected_via_org_endpoint_fallback(self):
        def fake_get(url, headers=None, timeout=None):
            self.calls.append((url, headers or {}))
            if url.startswith("https://api.github.com/users/acme-org"):
                return FakeResponse(404, {"message": "Not Found"})
            if url == "https://api.github.com/orgs/acme-org":
                return FakeResponse(200, {"login": "acme-org"})
            if url.startswith("https://api.github.com/orgs/acme-org/repos"):
                return FakeResponse(200, [
                    make_repo("acme-org", "org-repo"),
                    make_repo("bob", "bob-repo"),
                ])
            return FakeResponse(404, {})

        with mock.patch.object(lib.requests, "get", fake_get):
            repos = lib.search_user_repos("acme-org")

        self.assertEqual([repo["name"] for repo in repos], ["org-repo"])
        self.assertIn(
            "https://api.github.com/orgs/acme-org/repos?type=all&per_page=100&page=1",
            self.urls(),
        )

    def test_unknown_account_type_falls_back_to_user_endpoint(self):
        def fake_get(url, headers=None, timeout=None):
            self.calls.append((url, headers or {}))
            if url.startswith("https://api.github.com/users/foo/repos"):
                return FakeResponse(200, [
                    make_repo("foo", "foo-repo"),
                    make_repo("bar", "bar-repo"),
                ])
            return FakeResponse(404, {})

        with mock.patch.object(lib.requests, "get", fake_get):
            repos = lib.search_user_repos("foo")

        self.assertEqual([repo["name"] for repo in repos], ["foo-repo"])
        self.assertIn(
            "https://api.github.com/users/foo/repos?type=owner&per_page=100&page=1",
            self.urls(),
        )

    def test_login_lookup_failure_still_uses_username_endpoint(self):
        def fake_get(url, headers=None, timeout=None):
            self.calls.append((url, headers or {}))
            if url == "https://api.github.com/user":
                return FakeResponse(500, {"message": "boom"})
            if url == "https://api.github.com/users/alice":
                return FakeResponse(200, {"login": "alice", "type": "User"})
            if url.startswith("https://api.github.com/users/alice/repos"):
                return FakeResponse(200, [make_repo("alice", "public-repo")])
            return FakeResponse(404, {})

        with mock.patch.object(lib.requests, "get", fake_get):
            repos = lib.search_user_repos("alice", token="ghp_test")

        self.assertEqual([repo["name"] for repo in repos], ["public-repo"])


if __name__ == "__main__":
    unittest.main()
