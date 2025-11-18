"""Parser for TLD HTML pages from IANA."""

import logging
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class MainContentExtractor(HTMLParser):
    """HTML parser to extract content within <main> tags."""

    def __init__(self):
        super().__init__()
        self.in_main = False
        self.main_content = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
        if self.in_main:
            attrs_str = "".join(f' {k}="{v}"' for k, v in attrs)
            self.main_content.append(f"<{tag}{attrs_str}>")

    def handle_endtag(self, tag):
        if self.in_main:
            self.main_content.append(f"</{tag}>")
        if tag == "main":
            self.in_main = False

    def handle_data(self, data):
        if self.in_main:
            self.main_content.append(data)

    def get_main_content(self):
        """Return the extracted main content as a string."""
        return "".join(self.main_content)


def extract_main_content(html: str) -> str:
    """
    Extract the <main> content from full HTML.

    Args:
        html: Full HTML page content

    Returns:
        Just the <main>...</main> content, or empty string if no main tag
    """
    try:
        parser = MainContentExtractor()
        parser.feed(html)
        return parser.get_main_content()
    except Exception as e:
        logger.error("Error parsing HTML: %s", e)
        return ""
