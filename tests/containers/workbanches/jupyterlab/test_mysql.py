

from tests.containers.workbenches.workbench_image_test import WorkbenchContainer


def test_mysql_connection(mysql_container: MySqlContainer, workbench_image, subtests):
    with WorkbenchContainer(image=workbench_image) as workbench_container:
        # Get connection details from the container
        host = mysql_container.get_container_host_ip()
        port = mysql_container.get_exposed_port(3306)
        username = mysql_container.username
        password = mysql_container.password

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

        # Execute the python script inside the workbench container
        exit_code, (stdout, stderr) = workbench_container.exec_run(
            f"python -c '{python_script}'"
        )

        with subtests.test("Checking the output of the python script..."):
            assert exit_code == 0
            assert "MySQL connection successful!" in stdout.decode()
