class Image:

    def __init__(self, name=None, version=None, packages=None, components=None):
        self._name = name
        self._version = version
        self._packages = packages
        self._components = components if components is not None else []

    @classmethod
    def attributes(cls):
        """Show available attributes"""
        return ['name', 'version', 'packages', 'components']

    @classmethod
    def describe(cls):
        """Describe the Image class"""
        print("Image class attributes:")
        for attr in cls.attributes():
            print(f"  - {attr}")

    @property
    def name(self):
        return self._name

    @property
    def version(self):
        return self._version

    @property
    def components(self):
        return self._components

    @property
    def packages(self):
        return self._packages
