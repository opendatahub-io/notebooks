class Component:

    def __init__(self, name=None, path=None, attributes=None):
        self._name = name
        self._path = path
        self._attributes = attributes

    @property
    def name(self):
        return self._name

    @property
    def path(self):
        return self._path

    @property
    def attributes(self):
        return self._attributes
