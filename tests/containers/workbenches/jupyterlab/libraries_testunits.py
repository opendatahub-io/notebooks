import os
import unittest

"""This is run inside images by libraries_test.py"""

# Suppress noisy logs from libraries, especially during testing
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["KMP_WARNINGS"] = "0"


# ruff: noqa: PLC0415 `import` should be at the top-level of a file
class TestDataScienceLibs(unittest.TestCase):
    """A test suite to verify the basic functionality of key data science libraries."""

    @classmethod
    def setUpClass(cls):
        """Set up data once for all tests in this class."""
        print("--- 🧪 Verifying Data Science Environment ---")
        cls.image = os.environ["IMAGE"]
        print(f"Image: {cls.image}")

    def setUp(self):
        self.tear_downs = []

    def tearDown(self):
        """Clean up resources after all tests in this class have run."""
        for tear_down in self.tear_downs:
            tear_down()
        super().tearDown()

    def test_numpy(self):
        """Tests numpy array creation and basic operations."""
        import numpy as np  # pyright: ignore[reportMissingImports]

        arr = np.array([[1, 2], [3, 4]])
        self.assertEqual(arr.shape, (2, 2), "Numpy array shape is incorrect.")
        self.assertEqual(np.sum(arr), 10, "Numpy sum calculation is incorrect.")
        print("✅ NumPy test passed.")

    def test_pandas(self):
        """Tests pandas DataFrame creation."""
        import pandas as pd  # pyright: ignore[reportMissingImports]

        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        self.assertIsInstance(df, pd.DataFrame, "Object is not a Pandas DataFrame.")
        self.assertEqual(df.shape, (2, 2), "Pandas DataFrame shape is incorrect.")
        print("✅ Pandas test passed.")

    def test_sklearn(self):
        """Tests scikit-learn model fitting."""
        from sklearn.cluster import KMeans  # pyright: ignore[reportMissingImports]
        from sklearn.datasets import make_blobs  # pyright: ignore[reportMissingImports]

        X, _y = make_blobs(n_samples=100, centers=3, random_state=42)

        model = KMeans(n_clusters=3, random_state=42, n_init="auto")
        model.fit(X)
        self.assertEqual(model.cluster_centers_.shape, (3, 2), "Cluster centers shape is incorrect.")
        self.assertIsNotNone(model.labels_, "Scikit-learn model failed to fit.")
        print("✅ Scikit-learn test passed.")

    def test_matplotlib(self):
        """Tests matplotlib plot creation and saving to a file."""
        import matplotlib.pyplot as plt  # pyright: ignore[reportMissingImports]
        from sklearn.datasets import make_blobs  # pyright: ignore[reportMissingImports]

        X, y = make_blobs(n_samples=50, centers=3, n_features=2, random_state=42)
        plot_filename = "matplotlib_unittest.png"

        fig, ax = plt.subplots()
        ax.scatter(X[:, 0], X[:, 1], c=y)
        ax.set_title("Matplotlib Unittest")
        plt.savefig(plot_filename)
        self.tear_downs.append(lambda: os.remove(plot_filename))
        plt.close(fig)  # Close the figure to free up memory

        self.assertTrue(os.path.exists(plot_filename), "Matplotlib did not create the plot file.")
        print("✅ Matplotlib test passed.")

    def test_torch(self):
        """🧪 Tests basic PyTorch tensor operations."""
        if "-pytorch-" not in self.image:
            self.skipTest("Not a Torch image")
        import torch  # pyright: ignore[reportMissingImports]

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tensor = torch.rand(2, 3, device=device)
        self.assertEqual(tensor.shape, (2, 3), "PyTorch tensor shape is incorrect.")
        self.assertTrue(str(tensor.device).startswith(device), "Tensor was not created on the correct device.")
        print(f"✅ PyTorch test passed (using device: {device}).")

    def test_torchvision(self):
        """🧪 Tests torchvision model loading and inference."""
        if "-pytorch-" not in self.image:
            self.skipTest("Not a Torch image")
        import torch  # pyright: ignore[reportMissingImports]
        import torchvision  # pyright: ignore[reportMissingImports]

        model = torchvision.models.resnet18(weights=None)  # Use weights=None for faster testing
        model.eval()
        dummy_input = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            output = model(dummy_input)
        self.assertEqual(output.shape, (1, 1000), "Torchvision model output shape is incorrect.")
        print("✅ Torchvision test passed.")

    def test_torchaudio(self):
        """🧪 Tests torchaudio waveform generation."""
        if "-pytorch-" not in self.image:
            self.skipTest("Not a Torch image")
        try:
            import torchaudio  # pyright: ignore[reportMissingImports]
        except ImportError:
            # TODO: determine if having torchaudio installed is a requirement
            self.skipTest("Torchaudio is not installed.")

        sample_rate = 16000
        waveform = torchaudio.functional.generate_sine(440, sample_rate=sample_rate, duration=0.5)
        self.assertEqual(waveform.shape, (1, 8000), "Torchaudio waveform shape is incorrect.")
        print("✅ Torchaudio test passed.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
