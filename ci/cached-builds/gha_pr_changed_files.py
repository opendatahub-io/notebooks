import json
import logging
import os
import pathlib
import re
import subprocess
import unittest
import urllib.request

PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent.resolve()


def get_github_token() -> str:
    github_token = os.environ['GITHUB_TOKEN']
    return github_token


# https://docs.github.com/en/graphql/guides/forming-calls-with-graphql
def compose_gh_api_request(pull_number: int, owner="opendatahub-io", repo="notebooks", per_page=100,
                           cursor="") -> urllib.request.Request:
    github_token = get_github_token()

    return urllib.request.Request(
        url="https://api.github.com/graphql",
        method="POST",
        headers={
            "Authorization": f"bearer {github_token}",
        },
        # https://docs.github.com/en/graphql/guides/using-the-explorer
        data=json.dumps({"query": f"""
{{
  repository(owner:"{owner}", name:"{repo}") {{
    pullRequest(number:{pull_number}) {{
      files(first:{per_page}, after:"{cursor}") {{
        edges {{
          node {{
            path
          }}
          cursor
        }}
      }}
    }}
  }}
}}
    """}).encode("utf-8"),
    )


def list_changed_files(owner: str, repo: str, pr_number: int, per_page=100) -> list[str]:
    files = []

    logging.debug("Getting list of changed files from GitHub API")

    CURSOR = ""
    while CURSOR is not None:
        request = compose_gh_api_request(pull_number=pr_number, owner=owner, repo=repo, per_page=per_page,
                                         cursor=CURSOR)
        response = urllib.request.urlopen(request)
        data = json.loads(response.read().decode("utf-8"))
        response.close()
        edges = data["data"]["repository"]["pullRequest"]["files"]["edges"]

        CURSOR = None
        for edge in edges:
            files.append(edge["node"]["path"])
            CURSOR = edge["cursor"]

    logging.debug(f"Determined {len(files)} changed files: {files[:5]} (..., printing up to 5)")
    return files


def analyze_build_directories(make_target) -> list[str]:
    directories = []

    pattern = re.compile(r"#\*# Image build directory: <(?P<dir>[^>]+)> #\(MACHINE-PARSED LINE\)#\*#\.\.\.")
    try:
        logging.debug(f"Running make in --just-print mode for target {make_target}")
        for line in subprocess.check_output(["make", make_target, "--just-print"], encoding="utf-8",
                                            cwd=PROJECT_ROOT).splitlines():
            if m := pattern.match(line):
                directories.append(m["dir"])
    except subprocess.CalledProcessError as e:
        print(e.stderr, e.stdout)
        raise

    logging.debug(f"Target {make_target} depends on files in directories {directories}")
    return directories


def should_build_target(changed_files: list[str], target_directories: list[str]) -> str:
    """Returns truthy if there is at least one changed file necessitating a build.
    Falsy (empty) string is returned otherwise."""
    for directory in target_directories:
        for changed_file in changed_files:
            if changed_file.startswith(directory):
                return changed_file
    return ""


def filter_out_unchanged(targets: list[str], changed_files: list[str]) -> list[str]:
    changed = []
    for target in targets:
        target_directories = analyze_build_directories(target)
        if reason := should_build_target(changed_files, target_directories):
            logging.info(f"✅ Will build {target} because file {reason} has been changed")
            changed.append(target)
        else:
            logging.info(f"❌ Won't build {target}")
    return changed


class SelTestsTest(unittest.TestCase):
    def test_compose_gh_api_request__call_without_asserting(self):
        request = compose_gh_api_request(pull_number=556, per_page=100, cursor="")
        print(request.data)

    def test_list_changed_files__pagination_works(self):
        changed_files = list_changed_files(owner="opendatahub-io", repo="notebooks", pr_number=556, per_page=1)
        assert set(changed_files) == {'codeserver/ubi9-python-3.9/Dockerfile',
                                      'codeserver/ubi9-python-3.9/run-code-server.sh'}

    def test_analyze_build_directories(self):
        directories = analyze_build_directories("jupyter-intel-pytorch-ubi9-python-3.9")
        assert set(directories) == {"base/ubi9-python-3.9",
                                    "intel/base/gpu/ubi9-python-3.9",
                                    "jupyter/intel/pytorch/ubi9-python-3.9"}
