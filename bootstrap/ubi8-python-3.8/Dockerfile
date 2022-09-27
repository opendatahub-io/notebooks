FROM registry.access.redhat.com/ubi8/python-38:latest

LABEL name="odh-bootstrap-ubi8-python-3.8" \
      summary="Python 3.8 bootstrap image" \
      description="Bootstrap image used for generating requirements.txt files"

RUN python -m pip install pip-tools==6.8.0
