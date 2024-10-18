import os

import pathlib

# Absolute path to the top level directory
ROOT_PATH = pathlib.Path(__file__).parent.parent

# Disable Dagger telemetry and PaaS offering
os.environ["DO_NOT_TRACK"]= "1"
os.environ["NOTHANKS"]= "1"
