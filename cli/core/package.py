class Package:

    def __init__(self, name=None, version=None):
        self._name = name
        self._version = version

    @property
    def name(self):
        return self._name

    @property
    def version(self):
        return self._version
