import contextlib
import importlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

main = importlib.import_module("dump_github.main")


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def fake_run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return mock.Mock(returncode=0)

    def test_token_is_passed_through_env_not_url(self):
        repo = {"name": "repo", "clone_url": "https://github.com/alice/repo.git"}
        with mock.patch.object(main.subprocess, "run", self.fake_run):
            main.clone_repo(repo, token="ghp_secret")

        cmd, kwargs = self.calls[0]
        self.assertEqual(cmd[0], "git")
        self.assertIn("clone", cmd)
        # Existing credential helpers are reset so a stale stored credential
        # cannot shadow the token supplied here.
        self.assertEqual(
            cmd[cmd.index("credential.helper=") - 1], "-c"
        )
        self.assertIn(
            "credential.helper={}".format(main.GIT_CREDENTIAL_HELPER), cmd
        )
        self.assertEqual(cmd[-1], "https://github.com/alice/repo.git")
        self.assertNotIn("ghp_secret", " ".join(cmd))
        self.assertNotIn("@github.com", cmd[-1])
        env = kwargs["env"]
        self.assertEqual(env["DUMP_GITHUB_TOKEN"], "ghp_secret")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")

    def test_env_keeps_the_rest_of_the_environment(self):
        repo = {"name": "repo", "clone_url": "https://github.com/alice/repo.git"}
        with mock.patch.dict(os.environ, {"KEEP_ME": "yes"}):
            with mock.patch.object(main.subprocess, "run", self.fake_run):
                main.clone_repo(repo, token="ghp_secret")

        env = self.calls[0][1]["env"]
        self.assertEqual(env["KEEP_ME"], "yes")
        self.assertIsNot(env, os.environ)

    def test_clone_without_token_stays_anonymous(self):
        repo = {"name": "repo", "clone_url": "https://github.com/alice/repo.git"}
        with mock.patch.object(main.subprocess, "run", self.fake_run):
            main.clone_repo(repo)

        cmd, kwargs = self.calls[0]
        self.assertEqual(cmd, ["git", "clone", "https://github.com/alice/repo.git"])
        self.assertIsNone(kwargs["env"])

    def test_version_flag(self):
        import contextlib
        import io

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(buf):
                main.main(["--version"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(buf.getvalue().strip(), "dump-github " + main.__version__)

    def test_credential_helper_outputs_the_env_token(self):
        """Run the real helper snippet through `git credential fill` if git exists."""
        import shutil
        import subprocess

        if not shutil.which("git"):
            self.skipTest("git is not installed")

        result = subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "credential.helper={}".format(main.GIT_CREDENTIAL_HELPER),
                "credential",
                "fill",
            ],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            env={**os.environ, "DUMP_GITHUB_TOKEN": "ghp_secret"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("username=x-access-token", result.stdout)
        self.assertIn("password=ghp_secret", result.stdout)
        self.assertNotIn("DUMP_GITHUB_TOKEN", result.stdout)


class CliBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def fake_run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return mock.Mock(returncode=0)

    def test_zip_without_token_uses_head_when_branch_unknown(self):
        repo = {"name": "repo", "full_name": "alice/repo"}
        with mock.patch.object(main.subprocess, "run", self.fake_run):
            main.download_zip("alice", repo, limit_size=0)

        cmd = self.calls[0][0]
        self.assertEqual(
            cmd[-1], "https://github.com/alice/repo/archive/HEAD.zip"
        )

    def test_zip_with_token_and_known_branch_uses_zipball_ref(self):
        repo = {
            "name": "repo",
            "full_name": "alice/repo",
            "default_branch": "main",
        }
        with mock.patch.object(main.subprocess, "run", self.fake_run):
            main.download_zip("alice", repo, token="ghp_test", limit_size=0)

        cmd = self.calls[0][0]
        self.assertIn(
            "https://api.github.com/repos/alice/repo/zipball/main", cmd
        )
        self.assertIn("Authorization: Bearer ghp_test", cmd)

    def test_zip_with_token_and_unknown_branch_omits_ref(self):
        repo = {"name": "repo", "full_name": "alice/repo"}
        with mock.patch.object(main.subprocess, "run", self.fake_run):
            main.download_zip("alice", repo, token="ghp_test", limit_size=0)

        cmd = self.calls[0][0]
        self.assertIn("https://api.github.com/repos/alice/repo/zipball", cmd)
        self.assertFalse(
            any("/zipball/" in part for part in cmd)
        )

    def test_listing_error_exits_nonzero_with_message(self):
        err = io.StringIO()
        with mock.patch.object(
            main,
            "search_user_repos",
            side_effect=main.GitHubAPIError(
                403, "API rate limit exceeded (HTTP 403)"
            ),
        ):
            with self.assertRaises(SystemExit) as caught:
                with contextlib.redirect_stderr(err):
                    main.main(["alice"])

        self.assertEqual(caught.exception.code, 1)
        self.assertIn("alice", err.getvalue())
        self.assertIn("rate limit", err.getvalue())

    def test_empty_listing_reports_message(self):
        err = io.StringIO()
        with mock.patch.object(main, "search_user_repos", return_value=[]):
            with contextlib.redirect_stderr(err):
                main.main(["alice"])

        self.assertIn("No public repositories found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
