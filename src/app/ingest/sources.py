"""Load and validate the official-source allow-list (data/sources.yaml).

Every document in the knowledge base must be listed here with its origin (provenance).
"""

# imports
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator

# Define project paths and rules
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCES_FILE = PROJECT_ROOT / "data" / "sources.yaml"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

FILE_EXTENSIONS = {"html": "html", "pdf": "pdf", "text": "txt"}
ID_PREFIX = {"passport": "ppt", "nid": "nid"}


# Define the Source model
class Source(BaseModel):
    """One official document, with its origin and dates."""

    id: str = Field(pattern=r"^(ppt|nid)-\d{3}$")
    title: str
    url: HttpUrl
    service: Literal["passport", "nid"]
    language: Literal["bn", "en", "mixed"]
    doc_type: Literal["html", "pdf", "text"]
    capture: Literal["download", "manual"]
    publisher: str
    published_date: date | None = None  # date printed on the document, if any
    last_updated_date: date | None = None  # "last updated" date shown on the page, if any
    verified_date: date  # the day YOU opened the source and checked it
    notes: str = ""

    # Find each source's local file path
    @property
    def local_path(self) -> Path:
        """Where the raw file lives, by convention: data/raw/<service>/<id>.<ext>."""
        return RAW_DIR / self.service / f"{self.id}.{FILE_EXTENSIONS[self.doc_type]}"

    # Ensure the ID matches the service
    @model_validator(mode="after")
    def id_matches_service(self) -> Source:
        if not self.id.startswith(ID_PREFIX[self.service]):
            raise ValueError(f"{self.id}: id prefix does not match service '{self.service}'")
        return self


# Define the complete source registry
class SourceRegistry(BaseModel):
    """The whole allow-list: allowed domains plus all sources."""

    allowed_domains: list[str]
    sources: list[Source]

    # Validate allow-list entries, unique IDs, and approved HTTPS domains.
    @model_validator(mode="after")
    def check_unique_ids_and_domains(self) -> SourceRegistry:
        # Allow only plain, normalized hostnames in the allow-list.
        for domain in self.allowed_domains:
            if (
                not domain
                or domain != domain.lower()
                or domain.endswith(".")
                or "*" in domain
                or "/" in domain
                or ":" in domain
                or "@" in domain
                or urlparse(f"https://{domain}").hostname != domain
                or "." not in domain
                or any(
                    not label
                    or len(label) > 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or not label.isascii()
                    or not all(char.isalnum() or char == "-" for char in label)
                    for label in domain.split(".")
                )
            ):
                raise ValueError(f"Invalid allowed domain: {domain!r}")

        # Duplicate IDs.
        counts = Counter(source.id for source in self.sources)
        duplicates = sorted(source_id for source_id, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"Duplicate source ids: {duplicates}")

        # Only HTTPS URLs on approved domains are permitted.
        for source in self.sources:
            parsed_url = urlparse(str(source.url))
            if parsed_url.scheme != "https":
                raise ValueError(f"{source.id}: source URL must use HTTPS")

            host = parsed_url.hostname or ""
            allowed = any(
                host == domain or host.endswith(f".{domain}") for domain in self.allowed_domains
            )
            if not allowed:
                raise ValueError(f"{source.id}: host '{host}' is not in allowed_domains")

        return self


# Load and validate the YAML registry
def load_registry(path: Path = SOURCES_FILE) -> SourceRegistry:
    """Read the YAML file and validate it. Raises an error if anything is wrong."""
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return SourceRegistry.model_validate(data)


class VisibleTextParser(HTMLParser):
    """Extract visible text while ignoring scripts and styles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)


def validate_file(path: Path, doc_type: str) -> tuple[bool, str]:
    """Check file format and whether it contains basic usable content."""

    if not path.is_file():
        return False, "file is missing"

    if path.stat().st_size == 0:
        return False, "file is empty"

    try:
        if doc_type == "html":
            parser = VisibleTextParser()
            parser.feed(path.read_text(encoding="utf-8", errors="replace"))
            visible_text = " ".join(parser.parts)

            if len(visible_text) < 200:
                return (
                    False,
                    f"too little visible HTML text ({len(visible_text)} characters)",
                )

            return True, f"visible text: {len(visible_text)} characters"

        if doc_type == "pdf":
            with path.open("rb") as file:
                signature = file.read(5)

            if signature != b"%PDF-":
                return False, "invalid PDF signature"

            return True, "PDF signature valid; text extraction not checked"

        if doc_type == "text":
            content = path.read_text(encoding="utf-8").strip()

            if not content:
                return False, "text file is empty"

            return True, f"text characters: {len(content)}"

        return False, f"unsupported document type: {doc_type}"

    except (OSError, UnicodeError, ValueError) as error:
        return False, f"could not validate file: {error}"


# Main validation and reporting function
def main() -> int:
    """Command-line check: validates the YAML and confirms every raw file exists."""
    # Handle invalid registry data
    try:
        registry = load_registry()
    except Exception as error:  # show any problem in a readable way
        print(f"INVALID sources.yaml:\n{error}")
        return 1

    # Check the raw files and their basic content
    invalid = 0

    for source in registry.sources:
        valid, detail = validate_file(source.local_path, source.doc_type)

        status = "OK     " if valid else "INVALID"
        invalid += 0 if valid else 1

        tags = f"{source.service}/{source.language}/{source.doc_type}"
        print(f"{status} {source.id}  [{tags}]  {source.title}")

        if not valid:
            print(f"         Reason: {detail}")

    # Summarize the results
    total = len(registry.sources)
    usable = total - invalid

    print(f"\nBy service : {dict(Counter(s.service for s in registry.sources))}")
    print(f"By language: {dict(Counter(s.language for s in registry.sources))}")
    print(f"{total} sources, {usable} passed basic checks, {invalid} need attention")

    return 1 if invalid else 0


# Run the file as a program
if __name__ == "__main__":
    sys.exit(main())
