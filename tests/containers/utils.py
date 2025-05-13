from tests.containers import conftest


def is_rstudio_image(my_image: str) -> bool:
    label = "-rstudio-"

    image_metadata = conftest.get_image_metadata(my_image)

    return label in image_metadata.labels["name"]
