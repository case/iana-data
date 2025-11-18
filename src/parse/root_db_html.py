"""Parser for IANA Root Zone Database HTML file."""

from html.parser import HTMLParser
from pathlib import Path

from ..config import SOURCE_DIR, SOURCE_FILES


class RootDBHTMLParser(HTMLParser):
    """HTML parser for extracting TLD data from Root Zone Database."""

    def __init__(self):
        super().__init__()
        self.entries = []
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.td_count = 0
        self.current_entry = {}
        self.current_td_data = []
        self.current_domain_from_href = None

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.td_count = 0
            self.current_entry = {}
            self.current_domain_from_href = None
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_td_data = []
        elif tag == "a" and self.in_td and self.td_count == 0:
            # Extract domain from href in first column (domain column)
            attrs_dict = dict(attrs)
            if "href" in attrs_dict:
                href = attrs_dict["href"]
                # Extract TLD from href like "/domains/root/db/xn--kpry57d.html"
                if "/domains/root/db/" in href:
                    domain = href.split("/domains/root/db/")[1].replace(".html", "")
                    self.current_domain_from_href = f".{domain}"

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            # Only add entries that have all required fields
            if (
                self.current_entry
                and "domain" in self.current_entry
                and "type" in self.current_entry
                and "manager" in self.current_entry
            ):
                self.entries.append(self.current_entry)
        elif tag == "td" and self.in_td:
            self.in_td = False
            # Store the TD data based on column position
            td_text = "".join(self.current_td_data).strip()
            if self.td_count == 0:
                # Domain column - use href if available (for IDNs), otherwise use text
                if self.current_domain_from_href:
                    self.current_entry["domain"] = self.current_domain_from_href
                elif td_text.startswith("."):
                    self.current_entry["domain"] = td_text
            elif self.td_count == 1:
                # Type column
                self.current_entry["type"] = td_text
            elif self.td_count == 2:
                # TLD Manager column
                self.current_entry["manager"] = td_text
                # Track delegation status
                self.current_entry["delegated"] = td_text != "Not assigned"
            self.td_count += 1

    def handle_data(self, data):
        if self.in_td:
            self.current_td_data.append(data)


def parse_root_db_html(filepath: Path | None = None) -> list[dict]:
    """
    Parse the Root Zone Database HTML file.

    Args:
        filepath: Path to the root zone HTML file (defaults to configured location)

    Returns:
        List of TLD entry dicts with keys:
        - domain: TLD domain (e.g., ".com")
        - type: IANA type tag (e.g., "generic", "country-code")
        - manager: TLD manager name
        - delegated: Boolean indicating if TLD is delegated
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["ROOT_ZONE_DB"]
    content = filepath.read_text()

    parser = RootDBHTMLParser()
    parser.feed(content)

    return parser.entries
