"""Parser for IANA Root Zone Database HTML file."""

from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


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


def parse_root_db_html(filepath: Path) -> dict:
    """
    Parse the Root Zone Database HTML file.

    Args:
        filepath: Path to the root zone HTML file

    Returns:
        Dict with analysis results:
        - total: Total number of TLD entries
        - by_type: Count of TLDs by type (generic, country-code, etc.)
        - total_idns: Total number of IDN TLDs (xn--)
        - idn_by_type: Count of IDN TLDs by type
        - delegated: Count of delegated TLDs
        - undelegated: Count of undelegated TLDs (manager is "Not assigned")
        - entries: List of all TLD entries with domain, type, manager, and delegated status
    """
    content = filepath.read_text()

    parser = RootDBHTMLParser()
    parser.feed(content)

    entries = parser.entries

    # Split entries into delegated and undelegated
    delegated_entries = [e for e in entries if e.get("delegated", True)]
    undelegated_entries = [e for e in entries if not e.get("delegated", True)]

    # Count delegated by type
    delegated_by_type = defaultdict(int)
    for entry in delegated_entries:
        delegated_by_type[entry["type"]] += 1

    # Count delegated IDNs (domains starting with .xn--)
    delegated_idn_entries = [e for e in delegated_entries if e.get("domain", "").startswith(".xn--")]
    delegated_total_idns = len(delegated_idn_entries)

    # Count delegated IDNs by type
    delegated_idn_by_type = defaultdict(int)
    for entry in delegated_idn_entries:
        delegated_idn_by_type[entry["type"]] += 1

    return {
        "total": len(entries),
        "delegated": {
            "total": len(delegated_entries),
            "by_type": dict(delegated_by_type),
            "total_idns": delegated_total_idns,
            "idn_by_type": dict(delegated_idn_by_type),
        },
        "undelegated": {
            "total": len(undelegated_entries),
        },
        "entries": entries,
    }
