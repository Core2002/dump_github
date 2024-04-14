### Github Dumper

Github Dumper is a Python program designed to search for users' GitHub repositories and download the repositories. This tool can be used to back up users' GitHub repositories in case they need them later.

**Install:**
```
pip install -U dump-github
```

**Usage:**
```
usage: dump-github [-h] [-d] [-p] [--token TOKEN] [--limit_size LIMIT_SIZE] username

Backup users github repo.

positional arguments:
  username

options:
  -h, --help            show this help message and exit
  -d, --download_zip    only download zip file
  -p, --print           only print urls
  --token TOKEN         github token
  --limit_size LIMIT_SIZE
                        limit size(MB) of download zip file, if 0 then no limit(default:100).

https://github.com/Core2002/dump_github
```
