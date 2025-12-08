"""Parser for TLD HTML pages from IANA."""

import ipaddress
import logging
import re
from html.parser import HTMLParser
from typing import Any

from selectolax.parser import HTMLParser as SelectolaxParser

logger = logging.getLogger(__name__)


def parse_tld_page(html: str) -> dict[str, Any]:
    """
    Parse a TLD detail page and extract structured data.

    Args:
        html: HTML content of the TLD page (can be full page or just <main> content)

    Returns:
        Dict with extracted data including:
        - tld_display: TLD as displayed in page (may be Unicode)
        - tld_iso: ISO country code for IDN ccTLDs
        - orgs: {tld_manager, admin, tech}
        - nameservers: list of {hostname, ipv4: [], ipv6: []}
        - registry_url, whois_server, rdap_server
        - tld_created, tld_updated
        - iana_reports: list of {title, date}
    """
    tree = SelectolaxParser(html)
    result: dict[str, Any] = {}

    # Extract TLD from h1
    h1 = tree.css_first("h1")
    if h1:
        match = re.search(r"Delegation Record for \.(.+)", h1.text())
        if match:
            result["tld_display"] = match.group(1)

    # Extract type description from first p
    for p in tree.css("p"):
        text = p.text().strip()
        if text.startswith("(") and ("top-level domain" in text.lower()):
            if "country-code" in text.lower():
                result["is_cctld"] = True
                # Check for IDN mapping
                iso_match = re.search(r"designated for two-letter country code ([A-Z]{2})", text)
                if iso_match:
                    result["tld_iso"] = iso_match.group(1).lower()
            elif "generic" in text.lower():
                result["is_generic"] = True
            break

    # Extract organizations by finding h2 elements and their content
    orgs: dict[str, str] = {}
    h2_elements = tree.css("h2")

    for h2 in h2_elements:
        h2_text = h2.text().strip().lower()

        if "cctld manager" in h2_text or "sponsoring organisation" in h2_text:
            # For TLD Manager, the org name is in the first <b> tag
            org = _extract_first_bold_after_h2(h2)
            if org:
                orgs["tld_manager"] = org
        elif "administrative contact" in h2_text:
            # For contacts, the org is on the line after the <b> tag
            org = _extract_org_after_h2(h2)
            if org:
                orgs["admin"] = org
        elif "technical contact" in h2_text:
            org = _extract_org_after_h2(h2)
            if org:
                orgs["tech"] = org

    if orgs:
        result["orgs"] = orgs

    # Extract nameservers from table (with IP addresses)
    nameservers: list[dict[str, Any]] = []
    for table in tree.css("table"):
        for row in table.css("tbody tr"):
            tds = row.css("td")
            if len(tds) >= 2:
                hostname = tds[0].text().strip()
                if not hostname:
                    continue

                # Parse IP addresses from second column
                ip_td = tds[1]
                ip_html = ip_td.html or ""
                ipv4_list: list[str] = []
                ipv6_list: list[str] = []

                # Split on <br> tags to get individual IPs
                ip_parts = re.split(r"<br\s*/?>(?:</br>)?", ip_html)
                for part in ip_parts:
                    # Strip HTML tags and whitespace
                    ip_text = re.sub(r"<[^>]+>", "", part).strip()
                    if not ip_text:
                        continue

                    # Classify and normalize
                    try:
                        addr = ipaddress.IPv4Address(ip_text)
                        ipv4_list.append(str(addr))
                    except ipaddress.AddressValueError:
                        try:
                            addr6 = ipaddress.IPv6Address(ip_text)
                            # Normalize to compressed form
                            ipv6_list.append(str(addr6))
                        except ipaddress.AddressValueError:
                            # Not a valid IP, skip
                            pass

                nameservers.append({
                    "hostname": hostname,
                    "ipv4": ipv4_list,
                    "ipv6": ipv6_list,
                })
        if nameservers:
            break  # Found the nameservers table

    if nameservers:
        result["nameservers"] = nameservers

    # Extract registry information using regex on full HTML
    # Registry URL
    url_match = re.search(r'URL for registration services:</b>\s*<a href="([^"]+)"', html)
    if url_match:
        result["registry_url"] = url_match.group(1)

    # WHOIS server
    whois_match = re.search(r"WHOIS Server:</b>\s*([^\s<]+)", html)
    if whois_match:
        result["whois_server"] = whois_match.group(1).strip()

    # RDAP server
    rdap_match = re.search(r"RDAP Server:\s*</b>\s*([^\s<]+)", html)
    if rdap_match:
        result["rdap_server"] = rdap_match.group(1).strip()

    # Extract dates
    date_p = tree.css_first("p > i")
    if date_p:
        text = date_p.text()
        updated_match = re.search(r"Record last updated (\d{4}-\d{2}-\d{2})", text)
        if updated_match:
            result["tld_updated"] = updated_match.group(1)

        created_match = re.search(r"Registration date (\d{4}-\d{2}-\d{2})", text)
        if created_match:
            result["tld_created"] = created_match.group(1)

    # Extract IANA reports
    iana_reports = []
    for li in tree.css("ul li"):
        link = li.css_first("a")
        if link:
            href = link.attributes.get("href")
            if href and "/reports/" in href:
                title = link.text().strip()
                li_text = li.text()
                date_match = re.search(r"\((\d{4}-\d{2}-\d{2})\)", li_text)
                if title and date_match:
                    iana_reports.append({
                        "title": title,
                        "date": date_match.group(1)
                    })

    if iana_reports:
        result["iana_reports"] = iana_reports

    return result


def _extract_first_bold_after_h2(h2_node) -> str:
    """
    Extract text from the first <b> tag after an h2 element.

    Used for TLD Manager/Sponsoring Organisation where the org name
    is directly in the bold tag.

    Args:
        h2_node: The h2 element node

    Returns:
        Bold text content, or empty string if not found
    """
    parent = h2_node.parent
    if not parent:
        return ""

    parent_html = parent.html
    if not parent_html:
        return ""

    h2_text = h2_node.text().strip()

    # Find the first <b> content after this h2
    pattern = rf"<h2>{re.escape(h2_text)}</h2>\s*\n?\s*<b>([^<]+)</b>"
    match = re.search(pattern, parent_html)
    if match:
        return match.group(1).strip()

    return ""


def _extract_org_after_h2(h2_node) -> str:
    """
    Extract organization name from content after an h2 element.

    The pattern is:
        <h2>Section Name</h2>
        <b>Name/Title</b><br></br>
        Organization Name<br></br>

    Args:
        h2_node: The h2 element node

    Returns:
        Organization name, or empty string if not found
    """
    # Get the parent and find content after this h2
    parent = h2_node.parent
    if not parent:
        return ""

    # Get the HTML of the parent and extract content after this h2
    parent_html = parent.html
    if not parent_html:
        return ""

    h2_text = h2_node.text().strip()

    # Find the section in the HTML
    # Look for pattern after the h2: <b>...</b><br><br> Org Name<br
    # Note: selectolax normalizes <br></br> to <br><br>
    pattern = rf"<h2>{re.escape(h2_text)}</h2>\s*\n?\s*<b>[^<]+</b><br><br>\s*\n?\s*([^<]+)<br"
    match = re.search(pattern, parent_html)
    if match:
        return match.group(1).strip()

    return ""


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
