FROM registry.access.redhat.com/ubi9/python-39:latest

LABEL name="odh-bootstrap-ubi9-python-3.9" \
      summary="Python 3.9 bootstrap image" \
      description="Bootstrap image used for generating requirements.txt files"

RUN python -m pip install pip-tools==6.11.0

