import json
import sys


def find_suitable_sha(suffix: str, required: list[str], skopeo_output: str) -> str:
    """Skopeo lists tags oldest to newest."""
    tags = list(json.loads(skopeo_output)["Tags"])

    sha_list: list[list[str]] = []
    for img in required:
        prefix = f"{img}-main_"
        shas = [
            t.removeprefix(prefix).removesuffix(suffix) for t in tags if t.startswith(prefix) and t.endswith(suffix)
        ]
        print(f"  {img}: {len(shas)} builds")
        sha_list.append(shas)

    common = set.intersection(*map(set, sha_list))
    if not common:
        print(f"::error::No SHA has all required images: {required}", file=sys.stderr)
        sys.exit(1)

    for sha in reversed(sha_list[0]):
        if sha in common:
            return sha
    raise RuntimeError("unreachable")


def test_find_suitable_sha__single():
    suffix = "_suffix"
    required = ["codeserver-ubi9-python-3.12"]
    skopeo_output = json.dumps({"Tags": ["codeserver-ubi9-python-3.12-main_abdcef_suffix"]})
    assert find_suitable_sha(suffix, required, skopeo_output) == "abdcef"


def test_find_suitable_sha__multiple():
    suffix = "_suffix"
    required = ["img-a", "img-b"]
    skopeo_output = json.dumps(
        {
            "Tags": [
                "img-a-main_old111_suffix",
                "img-b-main_old111_suffix",
                "img-a-main_new222_suffix",
                "img-b-main_new222_suffix",
            ]
        }
    )
    assert find_suitable_sha(suffix, required, skopeo_output) == "new222"


if __name__ == "__main__":
    test_find_suitable_sha__single()
    test_find_suitable_sha__multiple()
    print("OK")
