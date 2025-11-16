"""Analysis functions for IANA data files."""

from .root_db_html import analyze_root_db_html
from .tlds_txt import analyze_tlds_txt, get_tlds_analysis

__all__ = ["analyze_tlds_txt", "get_tlds_analysis", "analyze_root_db_html"]
