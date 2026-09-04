"""Pillow adapter for :class:`~app.domain.ports.ImageEncoderPort`.

Decodes a packaged raster, drops SVG / undecodable / pixel-bomb inputs, downscales
until the configured long-edge and encoded-byte caps both hold, and emits WebP
bytes hashed with sha256. Pillow stays in this module; domain and application
never import it.
"""

from __future__ import annotations

import hashlib
import warnings
from io import BytesIO

from PIL import Image

from app.core.config import get_settings
from app.domain.entities import EncodedRaster

# Honor Pillow's bomb check, and refuse to decode above this pixel count even
# when Pillow would only warn (a zip-bomb of pixels, not just bytes).
_MAX_PIXELS = 40_000_000
_WEBP_QUALITY = 80
_WEBP_METHOD = 4

_DROP = (
    OSError,
    ValueError,
    SyntaxError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
)


def _is_svg(data: bytes, content_type: str) -> bool:
    if "svg" in content_type.lower():
        return True
    head = data.lstrip()[:512].lower()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head)


def _for_webp(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "RGBa"}:
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA" if "transparency" in image.info else "RGB")
    if image.mode in {"LA", "La"}:
        return image.convert("RGBA")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _webp_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=_WEBP_QUALITY, method=_WEBP_METHOD)
    return buffer.getvalue()


def _fit(image: Image.Image, max_edge: int) -> Image.Image:
    width, height = image.size
    if max(width, height) <= max_edge:
        return image
    fitted = image.copy()
    fitted.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return fitted


class PillowImageEncoder:
    """``ImageEncoderPort`` backed by Pillow. Returns ``None`` to drop an asset."""

    def encode(self, data: bytes, *, content_type: str) -> EncodedRaster | None:
        if not data or _is_svg(data, content_type):
            return None
        settings = get_settings()
        max_edge = settings.media_max_edge_px
        max_bytes = settings.media_max_bytes
        try:
            return self._encode(data, max_edge=max_edge, max_bytes=max_bytes)
        except _DROP:
            return None

    def _encode(self, data: bytes, *, max_edge: int, max_bytes: int) -> EncodedRaster | None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as opened:
                width, height = opened.size
                if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
                    return None
                opened.load()
                working = _for_webp(opened)

        edge = max_edge
        while edge >= 1:
            fitted = _fit(working, edge)
            payload = _webp_bytes(fitted)
            if len(payload) <= max_bytes:
                digest = hashlib.sha256(payload).hexdigest()
                return EncodedRaster(data=payload, sha256=digest, content_type="image/webp")
            next_edge = max(fitted.size) // 2
            if next_edge >= edge:
                return None
            edge = next_edge
        return None
