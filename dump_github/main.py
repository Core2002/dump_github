import argparse
import os
import subprocess
from urllib.parse import quote

from .lib import search_user_repos

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

args = parser.parse_args()


def clone_repo(repo, token=""):
    name = repo["name"]
    url = repo["clone_url"]
    if token:
        url = url.replace(
            "https://",
            "https://x-access-token:{}@".format(quote(token, safe="")),
            1,
        )
    print("Clone repo: {}".format(name))
    subprocess.run(["git", "clone", url], check=False)


def download_zip(user_name, reop, token=""):
    ref = reop.get("default_branch") or "main"
    max_size = args.limit_size * 1000 * 1000
    file_name = "./{}_{}.zip".format(user_name, reop["name"])
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
        url = "https://api.github.com/repos/{}/{}/zipball/{}".format(
            user_name, reop["name"], ref
        )
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
        url = "https://github.com/{}/{}/archive/refs/heads/{}.zip".format(
            user_name, reop["name"], ref
        )
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


def main():
    token = (args.token or "").strip() or (os.environ.get("GITHUB_TOKEN") or "").strip()
    repos = search_user_repos(args.username, token)
    for repo in repos:
        if args.print == True:
            print(repo["clone_url"])
        elif args.download_zip == True:
            download_zip(args.username, repo, token)
        else:
            clone_repo(repo, token)


if __name__ == "__main__":
    main()
