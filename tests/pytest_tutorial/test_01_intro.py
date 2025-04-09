"""Welcome!
Welcome to our pytest-based testsuite.

This series of tests is designed to help you understand how pytest works,
and how we use it to test our workbench images."""


def test_hello_world():
    """There are three ways to specify a test in PyTest.
    This one is the most straightforward.

    In a file that in named test_*.py or *_test.py,
    define a function named test_*, and pytest will discover it and run it as a test."""

    # Assertions in pytest are usually done with the `assert` keyword.
    # Pytest does magicks to produce an "expected x but got y"-style message from this.
    # In normal Python code without pytest, we'd only get a generic AssertionError exception without these details.
    assert 2 + 2 == 4

    # We are ok with having multiple assertions in a single test.
    # Subtests are often useful in such situations. That will be covered later.
    pod = "placeholder_value"
    # The customizable failre message with a f-string is a practical way to report more context
    # about a test failure when the assertion is not met.
    assert 2 + 2 == 4, f"Expectations about {pod=} were not fulfilled."


"""Now it's a good time to run the test above for yourself.

```
uv run pytest tests/pytest_tutorial/test_01_intro.py -k test_hello_world
```

Try adjusting the numbers in one of the assertions, rerun, and see the test fail.
"""


class TestSomething:
    """Tests can be also defined in a class named Test*"""

    # def __init__(self):
    #     """Pytest test classes may not have a constructor (i.e., the __init__ method).
    #
    #     If you uncomment this method and run the test suite, you'd see something like this:
    #     tests/pytest_tutorial/test_01_intro.py:38
    #       /Users/jdanek/IdeaProjects/notebooks/tests/pytest_tutorial/test_01_intro.py:38: PytestCollectionWarning: cannot collect test class 'TestSomething' because it has a __init__ constructor (from: tests/pytest_tutorial/test_01_intro.py)
    #         class TestSomething:
    #
    #     and the test_something method below will not be run as a test."""

    def test_something(self):
        """Individual tests are methods in this class, and they are named test_* as usual."""
        assert True is not False


import unittest


class LegacyThing(unittest.TestCase):
    """Last option, tests can be defined using the unittest package in the standard library.
    Pytest is compatible with unittest and will run these tests just fine.

    The important aspect for test discovery is that the class inherits from unittest.TestCase."""

    @classmethod
    def setUpClass(cls):
        """This classmethod will be run before any tests."""

    def setUp(self):
        """This method will be run before each test method."""

    def test_something(self):
        """Test methods still need to adhere to the test_* naming pattern."""
        self.assertEqual(2 + 2, 4)

    def tearDown(self):
        """This method will be run after each test method"""

    @classmethod
    def tearDownClass(cls):
        """This method will be run after all test methods were run."""


"""Pytest runs in two phases: test collection and then test execution.
In the collection phase, all files matching the pattern (test_*.py or *_test.py) are imported and scanned
 for test functions and methods, and then pytest runs what it discovered.

# Only perform collection (test discovery), do not execute anything:
```
uv run pytest tests/pytest_tutorial/test_01_intro.py --collect-only
```

In the execution phase, the collected tests are executed.

Pytest will initialize and then tear down any fixtures the tests may be using, as needed.
This is the idiomatic way of handling unittest's setUp and tearDown in Pytest.
See one of the follow-up tutorials about fixtures for more.
"""


class TestCapture:
    def test_something_that_prints(self):
        """Pytest has a built-in mechanism for capturing stdout and stderr.
        This is enabled by default, and it causes all output to be printed at the end of a test run,
         and only for tests that have failed.
        While it makes sense for unittests, we use stdout to track progress in the long-running tests here.

        Therefore, in our `pytest.ini`, we have disabled the capture (and set less verbose exceptions output):

        ```
        [pytest]
        addopts = --capture=no --tb=short
        ```
        """
        print("Hello, world")
        # Uncomment the three lines below.
        # Without `--capture=no` you would never see the Hello, world printed while waiting.
        # the default value for `--capture` is `--capture=fd`.

        # import time
        # time.sleep(10)
        # assert False
