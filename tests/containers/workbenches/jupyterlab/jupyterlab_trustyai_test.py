from __future__ import annotations

from typing import TYPE_CHECKING

import allure

from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if TYPE_CHECKING:
    from tests.containers import conftest


class TestJupyterLabDatascienceImage:
    """Tests for JupyterLab Workbench images in this repository that have trustyai."""

    APP_ROOT_HOME = "/opt/app-root/src"

    @allure.issue("RHOAIENG-26843")
    @allure.description("Check that basic trustyai+scikit-learn functionality is working.")
    def test_trustyai_with_sklearn_smoke(self, jupyterlab_trustyai_image: conftest.Image) -> None:
        container = WorkbenchContainer(image=jupyterlab_trustyai_image.name, user=4321, group_add=[0])
        # language=Python
        test_script_content = '''
#!/usr/bin/env python3
"""
Standalone smoke test for TrustyAI-scikit-learn compatibility.
Can be run directly in the trustyai notebook environment.
"""

import sys
import traceback


def test_sklearn_trustyai_compatibility():
    """Test basic compatibility between TrustyAI and scikit-learn."""
    try:
        import numpy as np
        import pandas as pd
        import sklearn
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        import trustyai
        from trustyai.metrics.fairness.group import statistical_parity_difference
        from trustyai.model import output

        print(f"✓ Successfully imported all required packages")
        print(f"  - scikit-learn version: {sklearn.__version__}")
        print(f"  - trustyai version: {trustyai.__version__}")

        # Verify scikit-learn version is approximately 1.8.x
        sklearn_version = sklearn.__version__
        if not sklearn_version.startswith('1.8'):
            print(f"⚠️  Warning: Expected scikit-learn ~1.8.x, got {sklearn_version}")

        # Test basic sklearn functionality
        print("✓ Testing basic scikit-learn functionality...")
        np.random.seed(42)
        X = np.random.randn(100, 3)
        y = (X[:, 0] + X[:, 1] > 0).astype(int)

        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X, y)
        predictions = model.predict(X[:10])
        print(f"  - Model trained and made predictions: {predictions[:5]}")

        # Test TrustyAI functionality
        print("✓ Testing TrustyAI functionality...")
        protected_attr = np.random.choice([0, 1], size=len(X), p=[0.6, 0.4])

        df = pd.DataFrame(X, columns=['f1', 'f2', 'f3'])
        df['prediction'] = model.predict(X)
        df['protected'] = protected_attr
        favorable = output("income", dtype="number", value=1)

        # https://github.com/trustyai-explainability/trustyai-explainability-python-examples/blob/main/examples/GroupFairnessMetrics.ipynb
        spd = statistical_parity_difference(
            privileged=df[df.protected == 0],
            unprivileged=df[df.protected == 1],
            favorable=[favorable],
        )
        print(f"  - Statistical Parity Difference calculated: {spd:.3f}")

        # Test TrustyAI output creation
        outputs = [output(name=f"pred_{i}", dtype="number", value=float(pred))
                   for i, pred in enumerate(predictions[:3])]
        print(f"  - Created {len(outputs)} TrustyAI output instances")

        print("🎉 All compatibility tests passed!")
        return True

    except Exception as e:
        print(f"❌ Compatibility test failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_sklearn_trustyai_compatibility()
    sys.exit(0 if success else 1)
'''
        with container:
            container.start(wait_for_readiness=False)
            exit_code, output_str = container.exec_script(test_script_content, script_name="test_trustyai.py")

            print(f"Script output:\n{output_str}")

            assert exit_code == 0, f"Script execution failed with exit code {exit_code}. Output:\n{output_str}"
            assert "🎉 All compatibility tests passed!" in output_str
            assert "- Statistical Parity Difference calculated: 1.000" in output_str
