from nisar_hazard_watch.constants.explorations import Lens
from nisar_hazard_watch.services.lens_catalog import list_lenses

FIRE_CONTEXT_TERMS = ("NASA FIRMS", "VIIRS", "active-fire detections", "between the last two radar")
FORBIDDEN_TERMS = ("not provided", "three-date", "hectare", "probability")


def test_the_wildfire_lens_describes_the_fire_context_that_ships() -> None:
    # Arrange
    lenses = {lens.id: lens for lens in list_lenses()}

    # Act
    description = lenses[Lens.WILDFIRE].description

    # Assert
    for term in FIRE_CONTEXT_TERMS:
        assert term in description
    for term in FORBIDDEN_TERMS:
        assert term not in description.lower()
    assert "no cause or burned area is reported" in description
