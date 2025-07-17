from __future__ import annotations

import pathlib
import tempfile
import time
import typing

import allure

from tests.containers import conftest, docker_utils
from tests.containers.kubernetes_utils import TestFrame
from tests.containers.workbenches.workbench_image_test import WorkbenchContainer

import testcontainers.core.network
from testcontainers.mysql import MySqlContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.waiting_utils import wait_for_logs


if typing.TYPE_CHECKING:
    from tests.containers.conftest import Image

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

        slapd_container = DockerContainer("docker.io/osixia/openldap:1.5.0")
        slapd_container.with_network(network).with_network_aliases("slapd").with_env("LDAP_DOMAIN", "example.com").with_env("LDAP_ADMIN_PASSWORD", "secret")
        slapd_container.with_volume_mapping("/Users/jdanek/IdeaProjects/notebooks/tests/containers/workbenches/jupyterlab/mysql/sasldb.db", "/etc/sasldb2", "ro")
        #slapd_container.with_volume_mapping("/Users/jdanek/IdeaProjects/notebooks/tests/containers/workbenches/jupyterlab/mysql/mdb.ldif", "/etc/ldap/slapd.d/cn=config/olcDatabase={1}mdb.ldif", "rw")
        tf.defer(slapd_container.start())

        try:
            wait_for_logs(slapd_container, r"slapd starting", timeout=5)
        except TimeoutError:
            print("Container is not ready.")
            print(slapd_container.get_wrapped_container().logs(stdout=True, stderr=True))
            raise

        time.sleep(5)

        cmd = ["ldapadd", "-x", "-D", "cn=admin,dc=example,dc=com", "-w", "secret"]
        # r = slapd_container.exec(cmd)
        # print(r)
        exit_code, output = docker_utils.container_exec_with_stdin(
            slapd_container.get_wrapped_container(),
            cmd,
            """dn: ou=People,dc=example,dc=com
objectClass: organizationalUnit
ou: People"""
        )
        output_str = output.decode()
        print(f"ldapadd output: {output_str}")
        assert exit_code == 0, f"ldapadd failed with exit code {exit_code}, output: {output_str}"

        exit_code, output = docker_utils.container_exec_with_stdin(
            slapd_container.get_wrapped_container(),
            cmd,
            """dn: uid=testuser,ou=People,dc=example,dc=com
objectClass: inetOrgPerson
uid: testuser
sn: Test
cn: Test User
userPassword: testpassword"""
        )
        output_str = output.decode()
        print(f"ldapadd output: {output_str}")
        assert exit_code == 0, f"ldapadd failed with exit code {exit_code}, output: {output_str}"

        # ec, out = slapd_container.exec("saslpasswd2 -c -u example.com testuser")
        # assert ec == 0, out

        #         exit_code, output = docker_utils.container_exec_with_stdin(
        #             slapd_container.get_wrapped_container(),
        #             ["/bin/bash", "-c", "cat > /etc/ldap/slapd.d/cn=config/olcDatabase={1}mdb.ldif"],
        #             """dn: olcDatabase={1}mdb,cn=config
        # changetype: modify
        # add: olcSaslAuxprops
        # olcSaslAuxprops: sasldb"""
        #         )
        #         output_str = output.decode()
        #         print(f"ldapadd output: {output_str}")
        #         assert exit_code == 0, f"ldapadd failed with exit code {exit_code}, output: {output_str}"

        # 1. add a user to sasldb
        # docker_utils.container_exec(
        #     slapd_container.get_wrapped_container(),
        #     ["/bin/bash", "-c", "saslpasswd2 -c -u example.com testuser"]
        # )

        #docker_utils.container_cp(slapd_container.get_wrapped_container(),
        #                          src="/Users/jdanek/IdeaProjects/notebooks/tests/containers/workbenches/jupyterlab/mysql/sasldb.db",
        #                          dst="/etc/sasldb2")

        # 2. restart slapd so it re-reads sasldb
        #slapd_container.exec("pkill -HUP slapd")

        image = DockerImage(image="mysql-sasl-test", path=pathlib.Path(__file__).parent / "mysql")
        image.build()

        # container = MySqlContainer("docker.io/library/mysql:9.3.0").with_network(network).with_network_aliases("mysql")
        # tf.defer(container.start())

        mysql_container = DockerContainer(image=image.short_id)
        mysql_container.with_network(network).with_network_aliases("mysql").with_env("MYSQL_ROOT_PASSWORD", "rootpassword")
        tf.defer(mysql_container.start())
        try:
            wait_for_logs(mysql_container, r"mysqld: ready for connections.", timeout=10)
        except TimeoutError:
            print("Container is not ready.")
            print(mysql_container.get_wrapped_container().logs(stdout=True, stderr=True))
            raise
        print(mysql_container.get_wrapped_container().logs(stdout=True, stderr=True))
        print("Container is ready. Setting up test user...")

        host = "mysql"
        port = 3306
        # username = container.username
        password = "StrongRootPass!"

        # language=Python
        setup_mysql_user = f"""
import mysql.connector

conn = mysql.connector.connect(
    user='root',
    password='StrongRootPass!',
    host = "mysql",
    port = 3306,
)
cursor = conn.cursor()
print("Creating SASL user 'testuser'@'%'...")
# The user name 'testuser' must match the one created in the container's OS

#cursor.execute("CREATE USER 'testuser'@'%' IDENTIFIED WITH authentication_ldap_sasl;")
#cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'testuser'@'%';")

cursor.execute("CREATE USER 'clearpassuser'@'%' IDENTIFIED WITH caching_sha2_password BY 'clearpassword';")
cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'clearpassuser'@'%';")

cursor.execute("FLUSH PRIVILEGES;")
cursor.close()
conn.close()
print("Test user created successfully.")
"""

        # language=Python
        python_script = f"""
import mysql.connector

try:
    cnx = mysql.connector.connect(
        user='testuser',
        password='testpassword',
        host='{host}',
        port={port},
        # auth_plugin='authentication_ldap_sasl_client',
        auth_plugin='authentication_ldap_sasl',
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
        container.with_network(network)
        container.with_command("/bin/sh -c 'sleep infinity'")
        try:
            container.start(wait_for_readiness=False)

            with subtests.test("Setting the user..."):
                exit_code, output = container.exec(["python", "-c", setup_mysql_user])
                output_str = output.decode()

                print(output_str)

                assert "Test user created successfully." in output_str
                assert exit_code == 0

            with subtests.test("Checking the output of the python script..."):
                exit_code, output = container.exec(["python", "-c", python_script])
                output_str = output.decode()

                print(output_str)

                assert "MySQL connection successful!" in output_str
                assert exit_code == 0

            with subtests.test("Checking the output of the clearpassuser script..."):
                exit_code, output = container.exec(["python", "-c", clearpassuser])
                output_str = output.decode()

                print(output_str)

                assert "MySQL connection successful!" in output_str
                assert exit_code == 0
        finally:
            print("*****")
            print(mysql_container.get_wrapped_container().logs(stdout=True, stderr=True))
            docker_utils.NotebookContainer(container).stop(timeout=0)

def setup_mysql_user(cls):
    """
    Connects as root and creates the SASL-authenticated user.
    This user must match the Linux user created in run.sh ('testuser').
    """
    params = cls.get_connection_params()
    conn = mysql.connector.connect(
        user='root',
        password='rootpassword',
        **params
    )
    cursor = conn.cursor()
    print("Creating SASL user 'testuser'@'%'...")
    # The user name 'testuser' must match the one created in the container's OS
    cursor.execute("CREATE USER 'testuser'@'%' IDENTIFIED WITH authentication_ldap_sasl;")
    cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'testuser'@'%';")
    cursor.execute("FLUSH PRIVILEGES;")
    cursor.close()
    conn.close()
    print("Test user created successfully.")
