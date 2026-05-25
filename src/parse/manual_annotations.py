"""Parser for hand-curated per-TLD annotations.

Holds the editorial labels that have no canonical published source and so must
be maintained by hand: geographic_scope (for gTLDs that name a place) and
cultural_affiliation. The file is keyed by bare TLD; ccTLD->country scope is
derived in the build, not listed here.
"""

import logging
from pathlib import Path

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)


def parse_manual_annotations(filepath: Path | None = None) -> dict[str, dict[str, str]]:
    """
    Parse the manual per-TLD annotations file.

    Args:
        filepath: Path to the annotations JSON file (defaults to configured location)

    Returns:
        dict: Map of bare lowercase TLD to its annotation fields, e.g.
              {"eus": {"geographic_scope": "subdivision",
                       "cultural_affiliation": "basque"}}
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["ANNOTATIONS"]

    data = read_json_file(filepath, default={})

    return {tld.lower(): fields for tld, fields in data.items()}
