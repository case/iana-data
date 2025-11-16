"""Parsers for IANA data files."""

from .tlds_txt import parse_tlds_file, tlds_txt_content_changed

__all__ = ["parse_tlds_file", "tlds_txt_content_changed"]
