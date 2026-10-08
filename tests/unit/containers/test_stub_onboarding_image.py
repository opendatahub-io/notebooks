from tests.containers.conftest import is_stub_onboarding_image


def test_jupyter_universal_is_not_a_stub() -> None:
    assert not is_stub_onboarding_image("jupyter-universal-ubi9-python-3.12")
    assert not is_stub_onboarding_image(
        "ghcr.io/opendatahub-io/notebooks/workbench-images:"
        "jupyter-universal-ubi9-python-3.12-4725_merge_deadbeef_odh_linux_amd64"
    )


def test_standard_jupyter_images_are_not_stubs() -> None:
    assert not is_stub_onboarding_image("jupyter-minimal-ubi9-python-3.12")
    assert not is_stub_onboarding_image("jupyter-baseline-ubi9-python-3.12")
    assert not is_stub_onboarding_image(
        "ghcr.io/opendatahub-io/notebooks/workbench-images:"
        "jupyter-datascience-ubi9-python-3.12-on-pr-deadbeef"
    )
