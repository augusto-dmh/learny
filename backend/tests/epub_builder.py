"""Shared EPUB-packing primitives for synthetic test fixtures.

The documented public surface for building EPUB bytes as reviewable code: the
OPF container XML, a minimal XHTML document wrapper, and a ZIP packer with the
uncompressed leading ``mimetype`` entry the format requires. Both the structural
parser fixtures (``fixtures_epub``) and the golden evaluation book
(``golden_corpus``) build on these, so a fixture depends on this contract rather
than on another fixture module's internals.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

_XHTML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html xmlns="http://www.w3.org/1999/xhtml">\n'
    "<head><title>{title}</title></head>\n"
    "<body>\n{body}\n</body>\n</html>\n"
)

# The EPUB OCF container that points at ``content.opf`` as the package root.
CONTAINER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    "  <rootfiles>\n"
    '    <rootfile full-path="content.opf" '
    'media-type="application/oebps-package+xml"/>\n'
    "  </rootfiles>\n"
    "</container>\n"
)


def build_doc(title: str, body: str) -> str:
    """Wrap ``body`` HTML in a minimal XHTML content document titled ``title``."""
    return _XHTML.format(title=title, body=body)


def zip_epub(members: dict[str, str | bytes]) -> bytes:
    """Pack ``members`` into an EPUB ZIP with an uncompressed leading mimetype."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        for name, content in members.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()
