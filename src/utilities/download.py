"""Download utilities for IANA data files."""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import httpx2

from ..config import (
    IANA_URLS,
    IPTOASN_DIR,
    IPTOASN_FILE,
    IPTOASN_URL,
    SOURCE_DIR,
    SOURCE_FILES,
)
from .cache import is_cache_fresh, parse_cache_control_max_age
from .file_io import atomic_write_bytes
from .metadata import (
    load_metadata,
    record_iptoasn_fetch,
    save_metadata,
    utc_timestamp,
)
from .retry import make_request_with_retry

logger = logging.getLogger(__name__)


class InvalidPayloadError(ValueError):
    """A downloaded payload was fetched but is not usable; the stored file stands."""


# =============================================================================
# Public API
# =============================================================================


def download_file(
    key: str,
    url: str,
    filename: str,
    content_validator: Callable[[Path, str], bool] | None = None,
    transform: Callable[[str], bytes] | None = None,
) -> str:
    """
    Download a single file using conditional requests.

    This is the main public API for downloading files. Handles all aspects:
    - HTTP client creation
    - Conditional requests (If-Modified-Since, ETag)
    - Cache freshness checks
    - Metadata loading and saving
    - Directory creation
    - File writing

    Args:
        key: Metadata key for tracking this download
        url: URL to download from
        filename: Filename to save in SOURCE_DIR
        content_validator: Optional callback to check if content actually changed.
            Takes (filepath, new_content_text) and returns True if content changed.
            If returns False, file is not saved and "not_modified" is returned.
        transform: Optional callback converting the response body, decoded as
            UTF-8, into the bytes to save. For sources whose published file is
            derived from the fetched document. Raising from it makes the
            download fail rather than saving a partial file. When the result
            matches the file on disk, "not_modified" is returned.

    Returns:
        Status: "downloaded", "not_modified", or "error"
    """
    filepath = Path(SOURCE_DIR) / filename

    # Ensure source directory exists
    Path(SOURCE_DIR).mkdir(parents=True, exist_ok=True)

    metadata = load_metadata()

    with httpx2.Client(timeout=30.0, follow_redirects=True) as client:
        result = _download_file_impl(
            client=client,
            key=key,
            url=url,
            filepath=filepath,
            metadata=metadata,
            content_validator=content_validator,
            transform=transform,
        )

    # Save updated metadata
    save_metadata(metadata)

    return result


def download_iana_files() -> dict[str, str]:
    """
    Download all IANA data files using conditional requests.

    Uses a single HTTP client and metadata save for efficiency when
    downloading multiple files.

    Returns:
        A dict mapping source keys to their download status:
        - "downloaded": File was updated
        - "not_modified": File hasn't changed
        - "error": The fetch failed; the stored file stands
        - "invalid": The payload was fetched and rejected; the stored file stands

        Both failures leave the previous data usable, so a caller may continue.
    """
    # Lazy imports to avoid circular dependency
    from ..parse import (
        iana_tlds_json_content_changed,
        rdap_json_content_changed,
        tlds_txt_content_changed,
    )

    metadata = load_metadata()
    results: dict[str, str] = {}

    # Ensure source directory exists
    Path(SOURCE_DIR).mkdir(parents=True, exist_ok=True)

    schema_path = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS_SCHEMA"]
    schema_before = schema_path.read_bytes() if schema_path.exists() else None

    with httpx2.Client(timeout=30.0, follow_redirects=True) as client:
        for key, url in IANA_URLS.items():
            filename = SOURCE_FILES[key]
            filepath = Path(SOURCE_DIR) / filename

            # Use content validators to ignore timestamp-only changes
            content_validator = None
            payload_validator = None
            if key == "TLD_LIST":
                content_validator = tlds_txt_content_changed
            elif key == "RDAP_BOOTSTRAP":
                content_validator = rdap_json_content_changed
            elif key == "IANA_TLDS":
                content_validator = iana_tlds_json_content_changed
                payload_validator = _validate_iana_tlds_payload
            elif key == "IANA_TLDS_SCHEMA":
                payload_validator = _validate_iana_tlds_schema_payload

            results[key] = _download_file_impl(
                client=client,
                key=key,
                url=url,
                filepath=filepath,
                metadata=metadata,
                content_validator=content_validator,
                payload_validator=payload_validator,
            )

    _hold_back_schema_the_stored_data_breaks(schema_before, metadata, results)

    # Save updated metadata
    save_metadata(metadata)

    return results


def download_iptoasn() -> str:
    """
    Download the iptoasn combined TSV file.

    Downloads the gzipped file from iptoasn.com and saves it locally.
    This file is gitignored and used during build for ASN lookups.

    Returns:
        Status: "downloaded" or "error"
    """
    iptoasn_dir = Path(IPTOASN_DIR)
    iptoasn_dir.mkdir(parents=True, exist_ok=True)
    filepath = iptoasn_dir / IPTOASN_FILE

    try:
        logger.info("Downloading iptoasn data from %s...", IPTOASN_URL)
        with httpx2.Client(timeout=60.0, follow_redirects=True) as client:
            response = make_request_with_retry(client, IPTOASN_URL)

            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                size_mb = len(response.content) / (1024 * 1024)
                logger.info("  → %s (%.1f MB)", filepath, size_mb)
                stamp = utc_timestamp()
                record_iptoasn_fetch(checked_at=stamp, downloaded_at=stamp)
                return "downloaded"
            else:
                logger.error("HTTP %d for %s", response.status_code, IPTOASN_URL)
                return "error"
    except Exception as e:
        logger.error("Error downloading iptoasn: %s", e)
        return "error"


def get_iptoasn_path() -> Path:
    """
    Get the path to the iptoasn data file.

    Returns:
        Path to ip2asn-combined.tsv.gz
    """
    return Path(IPTOASN_DIR) / IPTOASN_FILE


# =============================================================================
# Internal Implementation
# =============================================================================


def _decode_json_payload(content: bytes) -> object:
    try:
        return json.loads(content.decode("utf-8"))
    except ValueError as exc:
        raise InvalidPayloadError(f"payload is not JSON: {exc}") from exc


def _validate_iana_tlds_payload(content: bytes) -> None:
    """Raise InvalidPayloadError unless ``content`` fits the stored schema and the parser."""
    from ..parse.iana_tlds_json import parse_iana_tlds
    from ..parse.iana_tlds_schema import iana_tlds_conformance_problems

    document = _decode_json_payload(content)
    schema_path = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS_SCHEMA"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidPayloadError(f"no stored schema to check against: {exc}") from exc
    if problems := iana_tlds_conformance_problems(document, schema):
        raise InvalidPayloadError("breaks the IANA schema: " + "; ".join(problems))
    try:
        parse_iana_tlds(document)
    except ValueError as exc:
        raise InvalidPayloadError(f"rejected by the parser: {exc}") from exc


def _validate_iana_tlds_schema_payload(content: bytes) -> None:
    """Raise InvalidPayloadError unless ``content`` is IANA's TLD JSON schema."""
    from ..parse.iana_tlds_schema import iana_tlds_schema_problems

    if problems := iana_tlds_schema_problems(_decode_json_payload(content)):
        raise InvalidPayloadError("; ".join(problems))


def _hold_back_schema_the_stored_data_breaks(
    schema_before: bytes | None, metadata: dict, results: dict[str, str]
) -> None:
    """Restore the old schema, as "invalid", when the stored TLD JSON breaks the new one."""
    from ..parse.iana_tlds_schema import iana_tlds_conformance_problems

    schema_path = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS_SCHEMA"]
    data_path = Path(SOURCE_DIR) / SOURCE_FILES["IANA_TLDS"]
    if results.get("IANA_TLDS_SCHEMA") != "downloaded" or not data_path.exists():
        return
    try:
        document = json.loads(data_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems = [f"cannot read the stored pair: {exc}"]
    else:
        problems = iana_tlds_conformance_problems(document, schema)
    if not problems:
        return

    logger.error(
        "Holding back the new IANA schema: stored data breaks it: %s", problems
    )
    if schema_before is None:
        schema_path.unlink(missing_ok=True)
    else:
        atomic_write_bytes(schema_path, schema_before)
    metadata.get("IANA_TLDS_SCHEMA", {}).pop("cache_data", None)
    results["IANA_TLDS_SCHEMA"] = "invalid"


def _drop_cache_from_other_url(key: str, url: str, metadata: dict) -> None:
    """Discard cache validators recorded against a different URL, or against none."""
    entry = metadata.get(key)
    if not entry or "cache_data" not in entry:
        return
    if entry["cache_data"].get("url") == url:
        return
    logger.info("Dropping cache data for %s: recorded against a different URL", key)
    del entry["cache_data"]


def _record_cache_data(
    key: str, url: str, response: httpx2.Response, metadata: dict, *, saved: bool
) -> None:
    """Store the response's validators; `saved` restarts the freshness window."""
    cache_data = metadata[key].setdefault("cache_data", {})
    cache_data["url"] = url

    if "etag" in response.headers:
        cache_data["etag"] = response.headers["etag"]
    if "last-modified" in response.headers:
        cache_data["last_modified"] = response.headers["last-modified"]

    if "cache-control" in response.headers:
        max_age = parse_cache_control_max_age(response.headers["cache-control"])
        if max_age:
            cache_data["cache_control"] = response.headers["cache-control"]
            cache_data["cache_max_age"] = str(max_age)
            if saved:
                # is_cache_fresh measures staleness from this timestamp.
                cache_data["last_downloaded"] = utc_timestamp()


def _download_file_impl(
    client: httpx2.Client,
    key: str,
    url: str,
    filepath: Path,
    metadata: dict,
    content_validator: Callable[[Path, str], bool] | None = None,
    transform: Callable[[str], bytes] | None = None,
    payload_validator: Callable[[bytes], None] | None = None,
) -> str:
    """
    Internal implementation for downloading a single file.

    Used by both download_file() and download_iana_files() to share logic
    while allowing efficient batching with a single client/metadata.

    Args:
        client: httpx2 Client instance
        key: Metadata key for tracking this download
        url: URL to download from
        filepath: Local path to save file to
        metadata: Metadata dict (modified in place)
        content_validator: Optional callback to check if content actually changed.
        transform: Optional callback converting the response body into the bytes
            to save. See download_file.
        payload_validator: Optional callback that raises InvalidPayloadError for
            a body that must not replace the stored file.

    Returns:
        Status: "downloaded", "not_modified", "error", or "invalid"
    """
    # Validators describe one URL. Repointing a key must not carry them across.
    _drop_cache_from_other_url(key, url, metadata)

    # Skipped for a transform: it never runs on this path, so an origin max-age
    # would freeze the derived file. Why: docs/memory/log/2026-09-07-registry-agreement-csv.md
    if transform is None and key in metadata and is_cache_fresh(metadata[key]):
        logger.info("Cache still fresh for %s", key)
        # Update last_checked even for cache-fresh files
        if key not in metadata:
            metadata[key] = {}
        metadata[key]["last_checked"] = utc_timestamp()
        return "not_modified"

    # Prepare conditional request headers
    headers: dict[str, str] = {}
    if key in metadata and "cache_data" in metadata[key]:
        if "etag" in metadata[key]["cache_data"]:
            headers["If-None-Match"] = metadata[key]["cache_data"]["etag"]
        if "last_modified" in metadata[key]["cache_data"]:
            headers["If-Modified-Since"] = metadata[key]["cache_data"]["last_modified"]

    try:
        response = make_request_with_retry(client, url, headers=headers)

        # Initialize metadata entry if needed
        if key not in metadata:
            metadata[key] = {}

        # Always update last_checked timestamp
        metadata[key]["last_checked"] = utc_timestamp()

        if response.status_code == 304:
            # Not modified
            return "not_modified"
        elif response.status_code == 200:
            # Before anything is stored, so a rejected body earns no validators.
            if payload_validator is not None:
                payload_validator(response.content)

            # Check with content validator if provided
            if content_validator and not content_validator(filepath, response.text):
                # Recorded here too: a source that reports "unchanged" every
                # night would otherwise never send a validator again.
                _record_cache_data(key, url, response, metadata, saved=False)
                return "not_modified"

            if transform is None:
                content = response.content
            else:
                # Decoded explicitly: httpx2 infers a charset from the header and
                # would silently mangle a transform that must be byte-exact.
                content = transform(response.content.decode("utf-8"))

            # A derived file often outlives changes elsewhere in its source document.
            derived_unchanged = (
                transform is not None
                and filepath.exists()
                and filepath.read_bytes() == content
            )

            if not derived_unchanged:
                # Download successful: replace the stored file in one step
                atomic_write_bytes(filepath, content)

            # Only a response we processed to the end earns its validators. A
            # transform that raised must be retried, not answered with a 304.
            _record_cache_data(
                key, url, response, metadata, saved=not derived_unchanged
            )

            return "not_modified" if derived_unchanged else "downloaded"
        else:
            return "error"
    except InvalidPayloadError as e:
        logger.error("Invalid payload for %s, keeping the stored file: %s", key, e)
        return "invalid"
    except Exception as e:
        logger.error("Error downloading %s: %s", key, e)
        return "error"
