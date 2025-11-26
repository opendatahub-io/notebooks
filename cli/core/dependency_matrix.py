from .image import Image
from .package import Package

import numpy as np

class DependencyMatrix:

    def __init__(self):
        self._matrix = np.empty((3, 3), dtype=object)

    def get_matrix(self):
        return self._matrix

    def create_matrix(self, packages_per_image=2):
        for i in range(3):
            for j in range(3):
                packages = [Package(name=f"pkg_{i}_{j}_{k}") for k in range(packages_per_image)]
                self._matrix[i, j] = Image(name=f"image_{i}_{j}", packages=packages)
        return self._matrix
