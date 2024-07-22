import os

import pathlib

ROOT_PATH = pathlib.Path(__file__).parent.parent

os.environ["DO_NOT_TRACK"]= "1"
os.environ["NOTHANKS"]= "1"
