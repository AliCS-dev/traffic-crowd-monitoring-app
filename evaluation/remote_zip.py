"""A bounded HTTP range reader for Python's standard ZIP parser."""

import hashlib
import io
from urllib.request import Request, urlopen


class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url: str, size: int, *, byte_budget: int = 24_000_000):
        if not url.startswith("https://") or size <= 0 or byte_budget <= 0:
            raise ValueError("Expected HTTPS URL and positive size/budget")
        self.url = url
        self.size = size
        self.byte_budget = byte_budget
        self.position = 0
        self.downloaded_bytes = 0
        self.requests: list[dict] = []
        self._segments: list[tuple[int, bytes]] = []

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence not in (0, 1, 2):
            raise ValueError("Unknown seek origin")
        position = offset + (
            self.position if whence == 1 else self.size if whence == 2 else 0
        )
        if position < 0:
            raise ValueError("Negative seek")
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        start = self.position
        remaining = max(0, self.size - start)
        length = remaining if size < 0 else min(size, remaining)
        if length == 0:
            return b""
        for offset, data in self._segments:
            if offset <= start and start + length <= offset + len(data):
                self.position += length
                return data[start - offset : start - offset + length]
        if length > 8_000_000 or self.downloaded_bytes + length > self.byte_budget:
            raise ValueError("HTTP range download budget exceeded")
        end = start + length - 1
        # Distinct URLs prevent a cached signed redirect for a different byte range.
        separator = "&" if "?" in self.url else "?"
        request = Request(
            f"{self.url}{separator}byte_range={start}-{end}",
            headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
        )
        try:
            with urlopen(request, timeout=45) as response:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range")
                    != f"bytes {start}-{end}/{self.size}"
                ):
                    raise ValueError(
                        "Server did not return the exact requested byte range"
                    )
                data = response.read(length + 1)
                if len(data) != length:
                    raise ValueError("HTTP range response length mismatch")
        except OSError as error:
            # zipfile masks OSError from the end-record read as a corrupt archive.
            raise ValueError(f"HTTP range request failed: {error}") from error
        self.downloaded_bytes += length
        self.requests.append(
            {
                "start": start,
                "end": end,
                "bytes": length,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        self._segments.append((start, data))
        self.position += length
        return data
