"""Image encoder adapter — drop rules, WebP caps, and layer isolation.

Derived from the figure-extract acceptance criteria: SVG / undecodable /
pixel-bomb assets are dropped; PNG and JPEG become WebP under both caps;
identical input yields an identical sha256 of the encoded bytes; Pillow is not
imported from domain or application.
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.config import get_settings
from app.infrastructure.ingestion.images import PillowImageEncoder

_APP = Path(__file__).resolve().parents[1] / "app"
_PIL_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:PIL|pillow)\b")


def _raster(
    fmt: str,
    size: tuple[int, int] = (32, 16),
    color: tuple[int, int, int] = (10, 20, 30),
) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def _png_header(width: int, height: int) -> bytes:
    """A PNG whose IHDR claims ``width``×``height`` without storing that many pixels."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + chunk(b"IEND", b"")
    )


def _encode(data: bytes, content_type: str):
    return PillowImageEncoder().encode(data, content_type=content_type)


def test_svg_content_type_is_dropped() -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"></svg>'
    assert _encode(svg, "image/svg+xml") is None


def test_svg_markup_labelled_as_png_is_dropped() -> None:
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"></svg>'
    assert _encode(svg, "image/png") is None


def test_undecodable_bytes_are_dropped() -> None:
    assert _encode(b"not-a-raster", "image/png") is None


def test_pixel_bomb_is_dropped() -> None:
    # 10_000×10_000 exceeds the encoder's decode ceiling without allocating that
    # many pixels — the IHDR size is enough to refuse the asset.
    assert _encode(_png_header(10_000, 10_000), "image/png") is None


def test_png_becomes_webp_under_caps() -> None:
    result = _encode(_raster("PNG"), "image/png")
    assert result is not None
    assert result.content_type == "image/webp"
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()
    assert len(result.sha256) == 64
    assert result.sha256 == result.sha256.lower()
    settings = get_settings()
    assert len(result.data) <= settings.media_max_bytes
    with Image.open(BytesIO(result.data)) as encoded:
        assert encoded.format == "WEBP"
        assert max(encoded.size) <= settings.media_max_edge_px


def test_jpeg_becomes_webp_under_caps() -> None:
    result = _encode(_raster("JPEG"), "image/jpeg")
    assert result is not None
    assert result.content_type == "image/webp"
    assert len(result.data) <= get_settings().media_max_bytes
    with Image.open(BytesIO(result.data)) as encoded:
        assert encoded.format == "WEBP"
        assert max(encoded.size) <= get_settings().media_max_edge_px


def test_identical_input_yields_identical_sha256() -> None:
    png = _raster("PNG")
    first = _encode(png, "image/png")
    second = _encode(png, "image/png")
    assert first is not None and second is not None
    assert first.data == second.data
    assert first.sha256 == second.sha256


def test_oversize_long_edge_is_downscaled_under_cap() -> None:
    result = _encode(_raster("PNG", size=(2000, 100)), "image/png")
    assert result is not None
    settings = get_settings()
    assert len(result.data) <= settings.media_max_bytes
    with Image.open(BytesIO(result.data)) as encoded:
        assert max(encoded.size) <= settings.media_max_edge_px


def test_encoded_payload_never_exceeds_the_byte_cap(monkeypatch) -> None:
    # A tiny byte cap must not leak an oversize payload: downscale until it fits,
    # or drop the image.
    monkeypatch.setenv("LEARNY_MEDIA_MAX_BYTES", "80")
    get_settings.cache_clear()
    try:
        result = _encode(_raster("PNG", size=(400, 400), color=(1, 2, 3)), "image/png")
        if result is not None:
            assert len(result.data) <= 80
            assert result.content_type == "image/webp"
    finally:
        get_settings.cache_clear()


def test_pillow_is_not_imported_from_domain_or_application() -> None:
    offenders: list[str] = []
    for layer in ("domain", "application"):
        for path in (_APP / layer).rglob("*.py"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _PIL_IMPORT.match(line):
                    offenders.append(f"{path}:{lineno}:{line.strip()}")
    assert offenders == []
