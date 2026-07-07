import json
import sys


def find_suitable_sha(ref_prefix: str, tag_suffix: str, required: list[str], skopeo_output: str) -> str:
    """Skopeo lists tags oldest to newest.

    Image tags are formed as ``{target}-{ref_prefix}_{sha}{tag_suffix}``.
    """
    tags = list(json.loads(skopeo_output)["Tags"])

    sha_list: list[list[str]] = []
    for img in required:
        prefix = f"{img}-{ref_prefix}_"
        shas = [
            t.removeprefix(prefix).removesuffix(tag_suffix)
            for t in tags
            if t.startswith(prefix) and t.endswith(tag_suffix) and len(t) > len(prefix) + len(tag_suffix)
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
    skopeo_output = json.dumps({"Tags": ["codeserver-ubi9-python-3.12-main_abdcef_odh_linux_amd64"]})
    assert find_suitable_sha("main", "_odh_linux_amd64", ["codeserver-ubi9-python-3.12"], skopeo_output) == "abdcef"


def test_find_suitable_sha__rhoai_branch_without_suffix():
    skopeo_output = json.dumps({"Tags": ["jupyter-minimal-ubi9-python-3.12-rhoai-2.25_abc123def456"]})
    assert find_suitable_sha("rhoai-2.25", "", ["jupyter-minimal-ubi9-python-3.12"], skopeo_output) == "abc123def456"


def test_find_suitable_sha__multiple():
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
    assert find_suitable_sha("main", "_suffix", ["img-a", "img-b"], skopeo_output) == "new222"


if __name__ == "__main__":
    test_find_suitable_sha__single()
    test_find_suitable_sha__rhoai_branch_without_suffix()
    test_find_suitable_sha__multiple()
    print("OK")
