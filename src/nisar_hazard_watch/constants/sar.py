import re
from datetime import time
from enum import StrEnum

ASF_SEARCH_URL = "https://api.daac.asf.alaska.edu/services/search/param"
CATALOG_MAX_RESULTS = 500
WINDOW_DAYS = 152
MAX_IMAGES = 5
MIN_IMAGES = 4
SPACING_DAYS = 30
SPACING_TOLERANCE_DAYS = 6
FULL_COVERAGE = 0.95
# A user-chosen window: four passes at NISAR's 12-day repeat at least, and the gateway's year.
DATE_RANGE_MIN_DAYS = 36
DATE_RANGE_MAX_DAYS = 365
# The last second of the user's end date, so a pass that day is inside the window.
END_OF_DAY = time(23, 59, 59)

AOI_SIDE_KM = 10.24
MAX_POINT_LATITUDE = 89.9
UTM_NORTH_LIMIT = 84.0
UTM_SOUTH_LIMIT = -80.0
MAX_VERTICES = 100
MAX_POLYGONS = 10
NATIVE_PIXEL_M = 10
IDEAL_NATIVE_PIXELS = 1_100_000
MAX_NATIVE_PIXELS = 4_000_000
COORDINATE_DECIMALS = 5

SCENE_NAME_PATTERN = re.compile(
    r"^NISAR_L2_(?P<configuration>[A-Z]{2})_GCOV"
    r"_(?P<cycle>\d{3})_(?P<track>\d{3})_(?P<direction>[AD])_(?P<frame>\d{3})"
    r"_(?P<code>\d{4})_(?P<mode>[A-Z]{4})_[A-Z]"
    r"_(?P<start>\d{8}T\d{6})_\d{8}T\d{6}"
    r"_(?P<crid>[A-Z]\d{5})_[A-Z]_[A-Z]_[A-Z]_(?P<version>\d{3})$"
)
SCENE_TIME_FORMAT = "%Y%m%dT%H%M%S"
# A series key as SceneGroup.series_key writes it (as constants/insar.py SERIES_KEY reads it).
SERIES_KEY_PATTERN = r"^\d{3}_(?P<direction>[AD])_\d{3}_\d{4}_[A-Z0-9]{2,4}$"
FREQUENCY_A_MODE_LENGTH = 2


class AoiKind(StrEnum):
    POINT = "point"
    POLYGON = "polygon"


class Direction(StrEnum):
    ASCENDING = "A"
    DESCENDING = "D"


class Configuration(StrEnum):
    PRODUCTION = "PR"
    URGENT_RESPONSE = "UR"


class Maturity(StrEnum):
    UNVALIDATED = "unvalidated"
    BETA = "beta"
    PROVISIONAL = "provisional"
    VALIDATED = "validated"


MATURITY_RANK = {
    Maturity.UNVALIDATED: 0,
    Maturity.BETA: 1,
    Maturity.PROVISIONAL: 2,
    Maturity.VALIDATED: 3,
}
CONFIGURATION_RANK = {Configuration.URGENT_RESPONSE: 0, Configuration.PRODUCTION: 1}
MATURITY_BY_COLLECTION = {
    "NISAR_L2_GCOV_V1": Maturity.VALIDATED,
    "NISAR_L2_GCOV_PROVISIONAL_V1": Maturity.PROVISIONAL,
    "NISAR_L2_GCOV_BETA_V1": Maturity.BETA,
    "UR_L2_L_GCOV": Maturity.UNVALIDATED,
}
POLARIZATIONS_BY_MODE = {
    "SH": ["HH"],
    "SV": ["VV"],
    "DH": ["HH", "HV"],
    "DV": ["VV", "VH"],
    "QP": ["HH", "HV", "VH", "VV"],
    "QQ": ["HH", "HV", "VH", "VV"],
}


class PlanStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_HISTORY = "insufficientHistory"
    NO_COVERAGE = "noCoverage"
