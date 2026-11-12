import argparse
import os
import subprocess

from ._version import __version__
from .lib import search_user_repos

# One-shot credential helper: git asks for credentials, the helper answers with
# the token from the environment.  The token is therefore never part of the
# clone URL and never gets written to the cloned repository's .git/config.
GIT_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get || return 0; '
    'echo username=x-access-token; '
    'echo "password=$DUMP_GITHUB_TOKEN"; }; f'
)

parser = argparse.ArgumentParser(
    prog="dump-github",
    description="Backup users github repo.",
    epilog="https://github.com/Core2002/dump_github",
)

parser.add_argument("username")
parser.add_argument(
    "-d", "--download_zip", action="store_true", help="only download zip file"
)
parser.add_argument("-p", "--print", action="store_true", help="only print urls")
parser.add_argument(
    "--version", action="version", version="%(prog)s {}".format(__version__)
)
parser.add_argument(
    "--token",
    action="store",
    default="",
    help="GitHub personal access token (or set GITHUB_TOKEN). Required for private repos and higher API rate limits.",
)
parser.add_argument(
    "--limit_size",
    type=int,
    default=100,
    help="limit size(MB) of download zip file, if 0 then no limit(default:100).",
)


def clone_repo(repo, token=""):
    name = repo["name"]
    url = repo["clone_url"]
    cmd = ["git", "clone", url]
    env = None
    if token:
        # Use a credential helper instead of https://x-access-token:TOKEN@...
        # so the token does not leak into `ps` output or .git/config.
        cmd = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "credential.helper={}".format(GIT_CREDENTIAL_HELPER),
            "clone",
            url,
        ]
        env = os.environ.copy()
        env["DUMP_GITHUB_TOKEN"] = token
        env["GIT_TERMINAL_PROMPT"] = "0"
    print("Clone repo: {}".format(name))
    subprocess.run(cmd, env=env, check=False)


def download_zip(user_name, reop, token="", limit_size=100):
    ref = reop.get("default_branch") or "main"
    # Always archive the repository the API actually listed.  Using the
    # positional username here would point at the wrong owner whenever the
    # repo does not belong to that user.
    full_name = reop.get("full_name") or "{}/{}".format(user_name, reop["name"])
    max_size = limit_size * 1000 * 1000
    file_name = "./{}.zip".format(full_name.replace("/", "_"))
    curl_cmd = [
        "curl",
        "-sS",
        "-L",
        "--connect-timeout",
        "5",
        "--retry",
        "3",
        "--retry-delay",
        "3",
    ]
    if max_size > 0:
        curl_cmd.extend(["--max-filesize", str(max_size)])
    if token:
        url = "https://api.github.com/repos/{}/zipball/{}".format(full_name, ref)
        curl_cmd.extend(
            [
                "-H",
                "Authorization: Bearer {}".format(token),
                "-H",
                "Accept: application/vnd.github+json",
                "-o",
                file_name,
                url,
            ]
        )
    else:
        url = "https://github.com/{}/archive/refs/heads/{}.zip".format(full_name, ref)
        curl_cmd.extend(["-o", file_name, url])
    print("Download {} : {}".format(reop["name"], url))
    subprocess.run(curl_cmd, check=False)
    if (
        max_size > 0
        and os.path.exists(file_name)
        and os.stat(file_name).st_size > max_size
    ):
        os.remove(file_name)
        print("Removed {} because it exceeds the limit size.".format(file_name))


def main(argv=None):
    args = parser.parse_args(argv)
    token = (args.token or "").strip() or (os.environ.get("GITHUB_TOKEN") or "").strip()
    repos = search_user_repos(args.username, token)
    for repo in repos:
        if args.print:
            print(repo["clone_url"])
        elif args.download_zip:
            download_zip(args.username, repo, token, args.limit_size)
        else:
            clone_repo(repo, token)


if __name__ == "__main__":
    main()
