"""Politely download approved sources without overwriting existing files."""

import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.ingest.sources import load_registry, validate_file

USER_AGENT = "BanglaGovAssistantBot/0.1 (student capstone project)"
DELAY_SECONDS = 2
TIMEOUT_SECONDS = 30
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5


def is_approved_https_url(url: str, allowed_domains: list[str]) -> bool:
    """Accept HTTPS URLs only when their hostname matches an approved domain."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        return (
            parsed.scheme == "https"
            and host is not None
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)
        )
    except ValueError:
        return False


def allowed_by_robots(url: str, client: httpx.Client) -> bool:
    """Return True only when robots.txt permits this bot to fetch the URL."""
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"

    try:
        response = client.get(robots_url, follow_redirects=False)
    except httpx.HTTPError:
        return False

    if 300 <= response.status_code < 400:
        return False
    if response.status_code >= 500:
        return False
    if response.status_code >= 400:
        return True

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def download_source(
    client: httpx.Client,
    url: str,
    target: Path,
    doc_type: str,
    allowed_domains: list[str],
) -> tuple[bool, str]:
    """Download, validate, and atomically save one source without overwriting."""
    current_url = url

    for redirect_count in range(MAX_REDIRECTS + 1):
        if not is_approved_https_url(current_url, allowed_domains):
            return False, f"URL is not an approved HTTPS destination: {current_url}"

        if not allowed_by_robots(current_url, client):
            return False, f"robots.txt does not permit fetching {current_url}"

        try:
            with client.stream(
                "GET",
                current_url,
                follow_redirects=False,
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        return False, "redirect response has no Location header"
                    if redirect_count == MAX_REDIRECTS:
                        return False, "too many redirects"

                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()

                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        return False, "invalid Content-Length header"
                    if declared_size < 0 or declared_size > MAX_DOWNLOAD_BYTES:
                        return False, "download exceeds the 25 MiB size limit"

                target.parent.mkdir(parents=True, exist_ok=True)

                # Keep the temporary file beside the destination so replace is atomic.
                temp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        prefix=f".{target.name}.",
                        suffix=".part",
                        dir=target.parent,
                        delete=False,
                    ) as temp_file:
                        temp_path = Path(temp_file.name)
                        size = 0

                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_DOWNLOAD_BYTES:
                                return False, "download exceeds the 25 MiB size limit"
                            temp_file.write(chunk)

                    valid, detail = validate_file(temp_path, doc_type)
                    if not valid:
                        return False, f"downloaded content failed validation: {detail}"

                    # Hard-link creation fails if target already exists, avoiding overwrite.
                    try:
                        temp_path.hardlink_to(target)
                    except FileExistsError:
                        return False, "destination appeared during download; not overwritten"

                    return True, f"{size} bytes; {detail}"
                finally:
                    if temp_path is not None:
                        temp_path.unlink(missing_ok=True)

        except httpx.HTTPError as error:
            return False, f"HTTP error: {error}"
        except OSError as error:
            return False, f"file error: {error}"

    return False, "too many redirects"


def main() -> int:
    """Download registry entries marked capture=download."""
    try:
        registry = load_registry()
    except Exception as error:
        print(f"INVALID sources.yaml: {error}")
        return 1

    failures = 0
    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(
        headers=headers,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        for source in registry.sources:
            if source.capture != "download":
                continue

            target = source.local_path
            if target.exists():
                print(f"SKIP    {source.id} (file already exists)")
                continue

            success, detail = download_source(
                client=client,
                url=str(source.url),
                target=target,
                doc_type=source.doc_type,
                allowed_domains=registry.allowed_domains,
            )

            if success:
                print(f"SAVED   {source.id} -> {target} ({detail})")
            else:
                print(f"FAILED  {source.id}: {detail}")
                failures += 1

            time.sleep(DELAY_SECONDS)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
