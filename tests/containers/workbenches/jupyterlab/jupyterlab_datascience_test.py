from __future__ import annotations

import pathlib
import tempfile
import typing

import allure
import testcontainers.core.network
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.mysql import MySqlContainer

from tests.containers import conftest, docker_utils
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

if typing.TYPE_CHECKING:
    from tests.containers.conftest import Image
    from tests.containers.kubernetes_utils import TestFrame


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
    def test_mysql_connection(self, tf: TestFrame, datascience_image: Image, subtests):
        network = testcontainers.core.network.Network()
        tf.defer(network.create())

        mysql_container = (
            MySqlContainer("docker.io/library/mysql:9.3.0").with_network(network).with_network_aliases("mysql")
        )
        tf.defer(mysql_container.start())

        try:
            wait_for_logs(mysql_container, r"mysqld: ready for connections.", timeout=30)
        except TimeoutError:
            print("Container is not ready.")
            print(mysql_container.get_wrapped_container().logs(stdout=True, stderr=True))
            raise
        print("Container is ready. Setting up test user...")

        host = "mysql"
        port = 3306

        # language=Python
        setup_mysql_user = f"""
import mysql.connector

conn = mysql.connector.connect(
    user='root',
    password='{mysql_container.root_password}',
    host = "{host}",
    port = {port},
)
cursor = conn.cursor()
print("Creating test users...")

cursor.execute(
# language=mysql
'''
CREATE USER 'clearpassuser'@'%' IDENTIFIED WITH caching_sha2_password BY 'clearpassword';
GRANT ALL PRIVILEGES ON *.* TO 'clearpassuser'@'%';

FLUSH PRIVILEGES;
''')
cursor.close()
conn.close()
print("Test users created successfully.")
"""

        # language=Python
        clearpassuser = f"""
import mysql.connector

try:
    cnx = mysql.connector.connect(
        user='clearpassuser',
        password='clearpassword',
        host='{host}',
        port={port},
        auth_plugin='mysql_clear_password',
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
    raise
"""

        container = WorkbenchContainer(image=datascience_image.name, user=4321, group_add=[0])
        (container.with_network(network).with_command("/bin/sh -c 'sleep infinity'"))
        try:
            container.start(wait_for_readiness=False)

            # RHOAIENG-140: code-server image users are expected to install their own db clients
            if "-code-server-" in datascience_image.labels["name"]:
                exit_code, output = container.exec(
                    ["python", "-m", "pip", "install", "mysql-connector-python==9.3.0"]
                )
                output_str = output.decode()
                print(output_str)

                assert exit_code == 0, f"Failed to install mysql-connector-python: {output_str}"

            with subtests.test("Setting the user..."):
                exit_code, output = container.exec(["python", "-c", setup_mysql_user])
                output_str = output.decode()

                print(output_str)

                assert "Test users created successfully." in output_str
                assert exit_code == 0

            with subtests.test("Checking the output of the clearpassuser script..."):
                exit_code, output = container.exec(["python", "-c", clearpassuser])
                output_str = output.decode()

                print(output_str)

                assert "MySQL connection successful!" in output_str
                assert exit_code == 0
        finally:
            docker_utils.NotebookContainer(container).stop(timeout=0)
