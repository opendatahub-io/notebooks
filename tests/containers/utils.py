import docker.errors
import docker.models.images
import testcontainers.core.container


def is_rstudio_image(my_image: str) -> bool:
    label = "-rstudio-"

    client = testcontainers.core.container.DockerClient()
    try:
        image_metadata = client.client.images.get(my_image)
    except docker.errors.ImageNotFound:
        image_metadata = client.client.images.pull(my_image)
        assert isinstance(image_metadata, docker.models.images.Image)

    return label in image_metadata.labels["name"]
