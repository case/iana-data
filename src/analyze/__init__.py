"""Analysis functions for IANA data files."""

from .rdap_json import analyze_rdap_json
from .tlds_txt import analyze_tlds_txt, get_tlds_analysis

__all__ = [
    "analyze_rdap_json",
    "analyze_tlds_txt",
    "get_tlds_analysis",
]
