from __future__ import annotations

import pathlib
import tempfile
import typing

import allure

from tests.containers import conftest, docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if typing.TYPE_CHECKING:
    from testcontainers.mysql import MySqlContainer

class TestJupyterLabDatascienceImage:
    """Tests for JupyterLab Workbench images in this repository that are not -minimal-."""

    APP_ROOT_HOME = "/opt/app-root/src"

    @allure.issue("RHOAIENG-26843")
    @allure.description("Check that basic scikit-learn functionality is working.")
    def test_sklearn_smoke(self, jupyterlab_datascience_image: conftest.Image) -> None:
        container = WorkbenchContainer(image=jupyterlab_datascience_image.name, user=4321, group_add=[0])
        # language=Python
        test_script_content = """
import sklearn
from sklearn.linear_model import LogisticRegression
import numpy as np

# Set random seed for reproducibility
np.random.seed(42)

# Simple dataset
X = np.array([[1], [2], [3], [4], [5]])
y = np.array([0, 0, 1, 1, 1])

# Train a model
model = LogisticRegression(solver='liblinear', random_state=42)
model.fit(X, y)

# Make a prediction
pred = model.predict([[3.5]])
print(f"NumPy version: {np.__version__}")
print(f"Scikit-learn version: {sklearn.__version__}")
print(f"Prediction: {pred}")
# We expect class 1 for input 3.5
assert pred[0] == 1, "Prediction is not as expected"

print("Scikit-learn smoke test completed successfully.")
"""
        test_script_name = "test_sklearn.py"
        try:
            container.start(wait_for_readiness=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = pathlib.Path(tmpdir)
                script_path = tmpdir_path / test_script_name
                script_path.write_text(test_script_content)
                docker_utils.container_cp(
                    container.get_wrapped_container(),
                    src=str(script_path),
                    dst=self.APP_ROOT_HOME,
                )

            script_container_path = f"{self.APP_ROOT_HOME}/{test_script_name}"
            exit_code, output = container.exec(["python", script_container_path])
            output_str = output.decode()

            print(f"Script output:\n{output_str}")

            assert exit_code == 0, f"Script execution failed with exit code {exit_code}. Output:\n{output_str}"
            assert "Scikit-learn smoke test completed successfully." in output_str
            assert "Prediction: [1]" in output_str

        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)

    @allure.description("Check that mysql client functionality is working with SASL plain auth.")
    def test_mysql_connection(self, mysql_container: MySqlContainer, jupyterlab_datascience_image, subtests):
        host = mysql_container.get_container_host_ip()
        port = mysql_container.get_exposed_port(3306)
        username = mysql_container.username
        password = mysql_container.password

        container = WorkbenchContainer(image=jupyterlab_datascience_image.name, user=4321, group_add=[0])

        # language=Python
        python_script = f"""
import mysql.connector

try:
    cnx = mysql.connector.connect(
        user='{username}',
        password='{password}',
        host='{host}',
        port={port},
        auth_plugin='mysql_clear_password'
    )
    cursor = cnx.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    if result == (1,):
        print("MySQL connection successful!")
    else:
        print("MySQL connection failed!")
    cnx.close()
except Exception as e:
    print(f"An error occurred: {{e}}")
"""

        try:
            container.start(wait_for_readiness=True)
            exec = docker_utils.container_exec(container.get_wrapped_container(), f"python -c '{python_script}'")
            exit_code = exec.communicate()

            with subtests.test("Checking the output of the python script..."):
                assert exit_code == 0
                assert "MySQL connection successful!" in '\n'.join(exec.output)
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)
