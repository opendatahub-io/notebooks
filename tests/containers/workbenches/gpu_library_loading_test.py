"""Tests for GPU library loading in CUDA/ROCm images.

These tests verify that all required libraries can be loaded at runtime,
including lazily-loaded CUDA/ROCm modules that aren't caught by static ldd checks.

The tests can run without actual GPU hardware - they verify library loading,
not GPU computation. They use CPU fallback or catch expected "no GPU" errors
while still validating that libraries are properly installed.
"""

from __future__ import annotations

import binascii
import inspect
import json
import logging
import textwrap
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import types

import pydantic
import pytest

from tests.containers import conftest, docker_utils


class SymlinkCheckResult(pydantic.BaseModel):
    symlinks: dict[str, Any] = {}
    missing: list[str] = []
    broken: list[str] = []
    hipsparselt_in_rocm: bool = False


class LibLoadEntry(pydantic.BaseModel):
    lib: str
    path: str


class LibLoadFailure(pydantic.BaseModel):
    lib: str
    path: str
    error: str


class RocmLibCheckResult(pydantic.BaseModel):
    loaded: list[LibLoadEntry] = []
    failed: list[LibLoadFailure] = []
    not_found: list[str] = []
    missing_unversioned: list[str] = []
    rocm_lib: str


if TYPE_CHECKING:
    import pytest_subtests

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


def encode_python_function(python: str, function: types.FunctionType, *args: Any) -> list[str]:
    """Returns a cli command that will run the given Python function encoded inline."""
    code = textwrap.dedent(inspect.getsource(function))
    ccode = binascii.b2a_base64(code.encode())
    name = function.__name__
    parameters = ", ".join(repr(arg) for arg in args)
    program = textwrap.dedent(f"""
        import binascii;
        s=binascii.a2b_base64("{ccode.decode("ascii").strip()}");
        exec(s.decode());
        result = {name}({parameters});
        import json;
        print("RESULT>" + json.dumps(result));""")
    return [python, "-c", program]


class TestGPULibraryLoading:
    """Tests that verify GPU libraries can be loaded at runtime.

    These tests exercise code paths that trigger lazy loading of CUDA/ROCm modules,
    catching issues that static ldd checks would miss (e.g., when CUDA_MODULE_LOADING=LAZY).
    """

    def _run_in_container(
        self, image: str, test_fn: types.FunctionType, env: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Run a test function inside a container and return its result."""
        with docker_utils.running_container(image, user=1001, env=env) as container:
            cmd = encode_python_function("/opt/app-root/bin/python3", test_fn)
            ecode, output = container.exec(cmd)
            output_str = output.decode()
            if ecode != 0:
                pytest.fail(f"Container command failed with exit code {ecode}:\n{output_str}")

            for line in output_str.splitlines():
                LOGGER.debug(line)
                if line.startswith("RESULT>"):
                    return json.loads(line[len("RESULT>") :])

            pytest.fail(f"Test function did not return a result. Exit code: {ecode}, Output: {output_str}")

    @pytest.mark.parametrize("loading_mode", ["LAZY", "EAGER"])
    def test_pytorch_cuda_library_loading(self, cuda_image: str, subtests: pytest_subtests.SubTests, loading_mode: str):
        """Test that PyTorch CUDA libraries can be loaded."""
        image_metadata = conftest.get_image_metadata(cuda_image)
        if "-pytorch-" not in image_metadata.labels.get("name", ""):
            pytest.skip("Not a PyTorch image")

        def check_pytorch_cuda_libs():
            """Check PyTorch CUDA library loading - runs inside container."""
            import os

            results = {
                "imports": {},
                "operations": {},
                "loaded_libs": [],
                "errors": [],
            }

            # Test basic imports
            try:
                import torch  # type: ignore[reportMissingImports]  # container-only package

                results["imports"]["torch"] = True
                results["torch_version"] = torch.__version__
            except ImportError as e:
                results["imports"]["torch"] = False
                results["errors"].append(f"torch import: {e}")
                return results

            # Test CUDA availability check (triggers libcuda loading)
            try:
                cuda_available = torch.cuda.is_available()
                results["operations"]["cuda_is_available"] = cuda_available
            except Exception as e:
                results["operations"]["cuda_is_available"] = None
                results["errors"].append(f"cuda.is_available: {e}")

            # Test torchvision import (has its own native extensions)
            try:
                import torchvision  # type: ignore[reportMissingImports]  # container-only package

                results["imports"]["torchvision"] = True
                results["torchvision_version"] = torchvision.__version__
            except ImportError as e:
                results["imports"]["torchvision"] = False
                results["errors"].append(f"torchvision import: {e}")

            # Test torchaudio if present
            try:
                import torchaudio  # noqa: F401  # type: ignore[reportMissingImports]  # container-only package

                results["imports"]["torchaudio"] = True
            except ImportError:
                results["imports"]["torchaudio"] = False

            # Test CPU tensor operations (always should work)
            try:
                x = torch.randn(100, 100)
                _ = x @ x  # triggers BLAS
                results["operations"]["cpu_matmul"] = True
            except Exception as e:
                results["operations"]["cpu_matmul"] = False
                results["errors"].append(f"cpu_matmul: {e}")

            # Test nn.functional operations (triggers various backends)
            try:
                import torch.nn.functional as F  # noqa: N812  # type: ignore[reportMissingImports]  # container-only package

                x = torch.randn(1, 3, 32, 32)
                weight = torch.randn(16, 3, 3, 3)
                _ = F.conv2d(x, weight, padding=1)
                results["operations"]["cpu_conv2d"] = True
            except Exception as e:
                results["operations"]["cpu_conv2d"] = False
                results["errors"].append(f"cpu_conv2d: {e}")

            # If CUDA is available, test CUDA operations
            if results["operations"].get("cuda_is_available"):
                try:
                    x = torch.randn(100, 100, device="cuda")
                    _ = x @ x
                    results["operations"]["cuda_matmul"] = True
                except Exception as e:
                    results["operations"]["cuda_matmul"] = False
                    results["errors"].append(f"cuda_matmul: {e}")

                try:
                    x = torch.randn(1, 3, 32, 32, device="cuda")
                    weight = torch.randn(16, 3, 3, 3, device="cuda")
                    _ = torch.nn.functional.conv2d(x, weight, padding=1)
                    results["operations"]["cuda_conv2d"] = True
                except Exception as e:
                    results["operations"]["cuda_conv2d"] = False
                    results["errors"].append(f"cuda_conv2d: {e}")

            # List loaded shared libraries
            try:
                with open(f"/proc/{os.getpid()}/maps") as f:
                    for line in f:
                        if ".so" in line:
                            parts = line.split()
                            if len(parts) >= 6:
                                lib_path = parts[-1]
                                if lib_path.startswith("/") and lib_path not in results["loaded_libs"]:
                                    results["loaded_libs"].append(lib_path)
            except Exception as e:
                results["errors"].append(f"reading /proc/maps: {e}")

            return results

        env = {"CUDA_MODULE_LOADING": loading_mode}
        result = self._run_in_container(cuda_image, check_pytorch_cuda_libs, env=env)

        with subtests.test(f"torch import ({loading_mode})"):
            assert result["imports"].get("torch") is True, f"torch import failed: {result.get('errors')}"

        with subtests.test(f"torchvision import ({loading_mode})"):
            assert result["imports"].get("torchvision") is True, f"torchvision import failed: {result.get('errors')}"

        with subtests.test(f"cpu_matmul ({loading_mode})"):
            assert result["operations"].get("cpu_matmul") is True, f"CPU matmul failed: {result.get('errors')}"

        with subtests.test(f"cpu_conv2d ({loading_mode})"):
            assert result["operations"].get("cpu_conv2d") is True, f"CPU conv2d failed: {result.get('errors')}"

        # Log loaded libraries for debugging
        LOGGER.info(f"Loaded libraries ({loading_mode}): {len(result.get('loaded_libs', []))} libs")
        for lib in result.get("loaded_libs", []):
            if any(x in lib for x in ["cuda", "cublas", "cudnn", "nccl", "nvrtc", "torch"]):
                LOGGER.info(f"  GPU-related lib: {lib}")

    def test_pytorch_rocm_library_loading(self, rocm_image: str, subtests: pytest_subtests.SubTests):
        """Test that PyTorch ROCm libraries can be loaded."""
        image_metadata = conftest.get_image_metadata(rocm_image)
        if "-pytorch-" not in image_metadata.labels.get("name", ""):
            pytest.skip("Not a PyTorch image")

        def check_pytorch_rocm_libs():
            """Check PyTorch ROCm library loading - runs inside container."""
            import os

            results = {
                "imports": {},
                "operations": {},
                "loaded_libs": [],
                "errors": [],
                "env": {},
            }

            # Check ROCm environment
            results["env"]["ROCM_PATH"] = os.environ.get("ROCM_PATH", "not set")
            results["env"]["HIP_PATH"] = os.environ.get("HIP_PATH", "not set")

            # Test basic imports
            try:
                import torch  # type: ignore[reportMissingImports]  # container-only package

                results["imports"]["torch"] = True
                results["torch_version"] = torch.__version__
                results["torch_hip_version"] = getattr(torch.version, "hip", "N/A")
            except ImportError as e:
                results["imports"]["torch"] = False
                results["errors"].append(f"torch import: {e}")
                return results

            # Test ROCm/HIP availability
            try:
                # In ROCm builds, torch.cuda actually maps to HIP
                cuda_available = torch.cuda.is_available()
                results["operations"]["hip_is_available"] = cuda_available
            except Exception as e:
                results["operations"]["hip_is_available"] = None
                results["errors"].append(f"hip_is_available: {e}")

            # Test torchvision import
            try:
                import torchvision  # type: ignore[reportMissingImports]  # container-only package

                results["imports"]["torchvision"] = True
                results["torchvision_version"] = torchvision.__version__
            except ImportError as e:
                results["imports"]["torchvision"] = False
                results["errors"].append(f"torchvision import: {e}")

            # Test CPU operations (always should work)
            try:
                x = torch.randn(100, 100)
                _ = x @ x
                results["operations"]["cpu_matmul"] = True
            except Exception as e:
                results["operations"]["cpu_matmul"] = False
                results["errors"].append(f"cpu_matmul: {e}")

            try:
                import torch.nn.functional as F  # noqa: N812  # type: ignore[reportMissingImports]  # container-only package

                x = torch.randn(1, 3, 32, 32)
                weight = torch.randn(16, 3, 3, 3)
                _ = F.conv2d(x, weight, padding=1)
                results["operations"]["cpu_conv2d"] = True
            except Exception as e:
                results["operations"]["cpu_conv2d"] = False
                results["errors"].append(f"cpu_conv2d: {e}")

            # List loaded shared libraries
            try:
                with open(f"/proc/{os.getpid()}/maps") as f:
                    for line in f:
                        if ".so" in line:
                            parts = line.split()
                            if len(parts) >= 6:
                                lib_path = parts[-1]
                                if lib_path.startswith("/") and lib_path not in results["loaded_libs"]:
                                    results["loaded_libs"].append(lib_path)
            except Exception as e:
                results["errors"].append(f"reading /proc/maps: {e}")

            return results

        result = self._run_in_container(rocm_image, check_pytorch_rocm_libs)

        with subtests.test("torch import"):
            assert result["imports"].get("torch") is True, f"torch import failed: {result.get('errors')}"

        with subtests.test("torchvision import"):
            assert result["imports"].get("torchvision") is True, f"torchvision import failed: {result.get('errors')}"

        with subtests.test("cpu_matmul"):
            assert result["operations"].get("cpu_matmul") is True, f"CPU matmul failed: {result.get('errors')}"

        with subtests.test("cpu_conv2d"):
            assert result["operations"].get("cpu_conv2d") is True, f"CPU conv2d failed: {result.get('errors')}"

        # Log ROCm-related loaded libraries
        LOGGER.info(f"Loaded libraries: {len(result.get('loaded_libs', []))} libs")
        for lib in result.get("loaded_libs", []):
            if any(x in lib for x in ["hip", "rocm", "roc", "mio", "amd", "torch"]):
                LOGGER.info(f"  ROCm-related lib: {lib}")

    def test_tensorflow_cuda_library_loading(self, cuda_image: str, subtests: pytest_subtests.SubTests):
        """Test that TensorFlow CUDA libraries can be loaded."""
        image_metadata = conftest.get_image_metadata(cuda_image)
        if "-tensorflow-" not in image_metadata.labels.get("name", ""):
            pytest.skip("Not a TensorFlow image")

        def check_tensorflow_cuda_libs():
            """Check TensorFlow CUDA library loading - runs inside container."""
            import os

            os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"  # Suppress TF warnings

            results = {
                "imports": {},
                "operations": {},
                "devices": [],
                "errors": [],
            }

            try:
                import tensorflow as tf  # type: ignore[reportMissingModuleSource]  # container-only package

                results["imports"]["tensorflow"] = True
                results["tf_version"] = tf.__version__
            except ImportError as e:
                results["imports"]["tensorflow"] = False
                results["errors"].append(f"tensorflow import: {e}")
                return results

            # Check available devices
            try:
                devices = tf.config.list_physical_devices()
                results["devices"] = [{"name": d.name, "type": d.device_type} for d in devices]
                results["operations"]["list_devices"] = True
            except Exception as e:
                results["operations"]["list_devices"] = False
                results["errors"].append(f"list_devices: {e}")

            # Test CPU computation
            try:
                with tf.device("/CPU:0"):
                    x = tf.random.normal([100, 100])
                    y = tf.matmul(x, x)
                    _ = y.numpy()
                results["operations"]["cpu_matmul"] = True
            except Exception as e:
                results["operations"]["cpu_matmul"] = False
                results["errors"].append(f"cpu_matmul: {e}")

            # Test conv2d on CPU
            try:
                with tf.device("/CPU:0"):
                    x = tf.random.normal([1, 32, 32, 3])
                    kernel = tf.random.normal([3, 3, 3, 16])
                    y = tf.nn.conv2d(x, kernel, strides=1, padding="SAME")
                    _ = y.numpy()
                results["operations"]["cpu_conv2d"] = True
            except Exception as e:
                results["operations"]["cpu_conv2d"] = False
                results["errors"].append(f"cpu_conv2d: {e}")

            return results

        result = self._run_in_container(cuda_image, check_tensorflow_cuda_libs)

        with subtests.test("tensorflow import"):
            assert result["imports"].get("tensorflow") is True, f"TensorFlow import failed: {result.get('errors')}"

        with subtests.test("list_devices"):
            assert result["operations"].get("list_devices") is True, f"list_devices failed: {result.get('errors')}"

        with subtests.test("cpu_matmul"):
            assert result["operations"].get("cpu_matmul") is True, f"CPU matmul failed: {result.get('errors')}"

        with subtests.test("cpu_conv2d"):
            assert result["operations"].get("cpu_conv2d") is True, f"CPU conv2d failed: {result.get('errors')}"

        LOGGER.info(f"TensorFlow devices: {result.get('devices')}")

    def test_tensorflow_rocm_library_loading(self, rocm_image: str, subtests: pytest_subtests.SubTests):
        """Test that TensorFlow ROCm libraries can be loaded."""
        image_metadata = conftest.get_image_metadata(rocm_image)
        if "-tensorflow-" not in image_metadata.labels.get("name", ""):
            pytest.skip("Not a TensorFlow image")

        def check_tensorflow_rocm_libs():
            """Check TensorFlow ROCm library loading - runs inside container."""
            import os

            os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

            results = {
                "imports": {},
                "operations": {},
                "devices": [],
                "errors": [],
            }

            try:
                import tensorflow as tf  # type: ignore[reportMissingModuleSource]  # container-only package

                results["imports"]["tensorflow"] = True
                results["tf_version"] = tf.__version__
            except ImportError as e:
                results["imports"]["tensorflow"] = False
                results["errors"].append(f"tensorflow import: {e}")
                return results

            try:
                devices = tf.config.list_physical_devices()
                results["devices"] = [{"name": d.name, "type": d.device_type} for d in devices]
                results["operations"]["list_devices"] = True
            except Exception as e:
                results["operations"]["list_devices"] = False
                results["errors"].append(f"list_devices: {e}")

            try:
                with tf.device("/CPU:0"):
                    x = tf.random.normal([100, 100])
                    y = tf.matmul(x, x)
                    _ = y.numpy()
                results["operations"]["cpu_matmul"] = True
            except Exception as e:
                results["operations"]["cpu_matmul"] = False
                results["errors"].append(f"cpu_matmul: {e}")

            try:
                with tf.device("/CPU:0"):
                    x = tf.random.normal([1, 32, 32, 3])
                    kernel = tf.random.normal([3, 3, 3, 16])
                    y = tf.nn.conv2d(x, kernel, strides=1, padding="SAME")
                    _ = y.numpy()
                results["operations"]["cpu_conv2d"] = True
            except Exception as e:
                results["operations"]["cpu_conv2d"] = False
                results["errors"].append(f"cpu_conv2d: {e}")

            return results

        result = self._run_in_container(rocm_image, check_tensorflow_rocm_libs)

        with subtests.test("tensorflow import"):
            assert result["imports"].get("tensorflow") is True, f"TensorFlow import failed: {result.get('errors')}"

        with subtests.test("list_devices"):
            assert result["operations"].get("list_devices") is True, f"list_devices failed: {result.get('errors')}"

        with subtests.test("cpu_matmul"):
            assert result["operations"].get("cpu_matmul") is True, f"CPU matmul failed: {result.get('errors')}"

        LOGGER.info(f"TensorFlow devices: {result.get('devices')}")

    def test_rocm_critical_library_loading(self, rocm_image: str, subtests: pytest_subtests.SubTests):
        """Verify critical ROCm compute libraries can be loaded via ctypes.

        Uses ctypes.cdll.LoadLibrary to attempt loading each critical ROCm library.
        This catches missing unversioned .so symlinks (RHAIENG-2643) as well as
        transitive dependency failures -- e.g., removing libhipblaslt.so breaks
        libhipblas, libMIOpen, librocblas, and librocsolver which depend on it.

        Works without GPU hardware. Applies to all ROCm images (TF and PyTorch).
        """

        def check_rocm_libs():
            """Attempt to load critical ROCm libraries - runs inside container."""
            import ctypes
            import glob
            import os

            rocm_path = os.environ.get("ROCM_PATH", "/opt/rocm")
            rocm_lib = os.path.join(rocm_path, "lib")

            critical_basenames = [
                "libhipblaslt",
                "libhipblas",
                "libMIOpen",
                "librocblas",
                "librocsolver",
                "librocfft",
                "librocrand",
                "librocsparse",
                "librccl",
            ]

            results = {"loaded": [], "failed": [], "not_found": [], "missing_unversioned": [], "rocm_lib": rocm_lib}

            for basename in critical_basenames:
                pattern = os.path.join(rocm_lib, f"{basename}.so*")
                matches = sorted(glob.glob(pattern))
                if not matches:
                    results["not_found"].append(basename)
                    continue

                unversioned = os.path.join(rocm_lib, f"{basename}.so")
                has_unversioned = os.path.exists(unversioned) or os.path.islink(unversioned)
                if not has_unversioned:
                    results["missing_unversioned"].append(basename)

                soname = unversioned if has_unversioned else matches[0]

                try:
                    ctypes.cdll.LoadLibrary(soname)
                    results["loaded"].append({"lib": basename, "path": soname})
                except OSError as e:
                    results["failed"].append({"lib": basename, "path": soname, "error": str(e)})

            return results

        raw = self._run_in_container(rocm_image, check_rocm_libs)
        result = RocmLibCheckResult.model_validate(raw)

        with subtests.test("all critical ROCm libs found"):
            assert len(result.not_found) == 0, (
                f"Critical ROCm libraries not found in {result.rocm_lib}: {result.not_found}"
            )

        with subtests.test("all critical ROCm libs have unversioned .so symlinks"):
            assert len(result.missing_unversioned) == 0, (
                f"Critical ROCm libraries missing unversioned .so symlinks in {result.rocm_lib} "
                f"(RHAIENG-2643): {result.missing_unversioned}"
            )

        with subtests.test("all critical ROCm libs loadable"):
            assert len(result.failed) == 0, (
                f"Critical ROCm libraries failed to load: {[(f.lib, f.error) for f in result.failed]}"
            )

        for entry in result.loaded:
            LOGGER.info(f"  ROCm lib OK: {entry.lib} ({entry.path})")
        for basename in result.missing_unversioned:
            LOGGER.warning(f"  ROCm lib missing unversioned symlink: {basename}.so")
        for failure in result.failed:
            LOGGER.error(f"  ROCm lib FAILED: {failure.lib} ({failure.path}): {failure.error}")


class TestLibrarySymlinks:
    """Tests that verify library symlinks are correctly set up."""

    def test_rocm_devendor_symlinks(self, rocm_image: str, subtests: pytest_subtests.SubTests):
        """Verify that PyTorch's de-vendored ROCm libraries are correctly symlinked."""
        image_metadata = conftest.get_image_metadata(rocm_image)
        if "-pytorch-" not in image_metadata.labels.get("name", ""):
            pytest.skip("Not a PyTorch image")

        def check_symlinks():
            """Check ROCm library symlinks in torch/lib."""
            import os

            results = {
                "symlinks": {},
                "missing": [],
                "broken": [],
            }

            torch_lib = "/opt/app-root/lib/python3.12/site-packages/torch/lib"
            rocm_lib = "/opt/rocm/lib"

            # Libraries that should be symlinked
            expected_symlinks = [
                "libamd_comgr.so",
                "libamdhip64.so",
                "libhipblaslt.so",
                "libhipblas.so",
                "libhipfft.so",
                "libhiprand.so",
                "libhiprtc.so",
                "libhipsolver.so",
                "libhipsparse.so",
                "libhsa-runtime64.so",
                "libMIOpen.so",
                "librccl.so",
                "librocblas.so",
                "librocfft.so",
                "librocm_smi64.so",
                "librocrand.so",
                "librocsolver.so",
                "librocsparse.so",
                "libroctracer64.so",
                "libroctx64.so",
            ]

            for lib in expected_symlinks:
                lib_path = os.path.join(torch_lib, lib)
                if os.path.exists(lib_path) or os.path.islink(lib_path):
                    if os.path.islink(lib_path):
                        target = os.readlink(lib_path)
                        if os.path.exists(lib_path):
                            results["symlinks"][lib] = {"target": target, "valid": True}
                        else:
                            results["symlinks"][lib] = {"target": target, "valid": False}
                            results["broken"].append(lib)
                    else:
                        results["symlinks"][lib] = {"target": "not a symlink", "valid": True}
                else:
                    results["missing"].append(lib)

            # Check if hipsparselt is available (may need to be added)
            hipsparselt_path = os.path.join(torch_lib, "libhipsparselt.so")
            if os.path.exists(hipsparselt_path) or os.path.islink(hipsparselt_path):
                results["symlinks"]["libhipsparselt.so"] = {"exists": True}
            else:
                # Check if it exists in ROCm
                rocm_hipsparselt = os.path.join(rocm_lib, "libhipsparselt.so.0")
                results["hipsparselt_in_rocm"] = os.path.exists(rocm_hipsparselt)

            return results

        with docker_utils.running_container(rocm_image, user=1001) as container:
            cmd = encode_python_function("/opt/app-root/bin/python3", check_symlinks)
            ecode, output = container.exec(cmd)
            if ecode != 0:
                pytest.fail(f"Symlink check failed with exit code {ecode}:\n{output.decode()}")

            result = None
            for line in output.decode().splitlines():
                if line.startswith("RESULT>"):
                    result = SymlinkCheckResult.model_validate(json.loads(line[len("RESULT>") :]))
                    break

            if result is None:
                pytest.fail(f"Failed to get symlink check result: {output.decode()}")
                return  # unreachable, but helps type narrowing

            with subtests.test("no broken symlinks"):
                assert len(result.broken) == 0, f"Broken symlinks: {result.broken}"

            with subtests.test("key symlinks present"):
                # Allow some libraries to be missing if they're optional
                critical_libs = ["libamdhip64.so", "librocblas.so", "libMIOpen.so", "libhipblaslt.so"]
                critical_missing = [lib for lib in critical_libs if lib in result.missing]
                assert len(critical_missing) == 0, f"Critical symlinks missing: {critical_missing}"

            LOGGER.info(f"Symlinks checked: {len(result.symlinks)}")
            LOGGER.info(f"Missing (may be optional): {result.missing}")
            if result.hipsparselt_in_rocm:
                LOGGER.warning("hipsparselt exists in ROCm but not symlinked to torch/lib")
