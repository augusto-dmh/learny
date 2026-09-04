"""Rewrite derived section markdown image destinations (figures at ingest).

Maps packaged hrefs onto ``/api/sources/{source_id}/media/{sha256}`` in markdown
only. HTML fragments are not an input; ``corpus_blocks.html_fragment`` is never
seen here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import UUID

_IMAGE = re.compile(r"!\[([^\]]*)]\(([^)]+)\)")


def rewrite_markdown_images(
    markdown: str,
    *,
    source_id: UUID,
    href_to_hash: Mapping[str, str],
) -> str:
    """Return markdown with mapped image hrefs replaced by same-origin media URLs.

    Unmapped destinations are left unchanged. Alt text is copied verbatim so
    metacharacters inside alt are not reinterpreted as nested markdown.
    """

    def replace(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2)
        digest = href_to_hash.get(src)
        if digest is None:
            return match.group(0)
        return f"![{alt}](/api/sources/{source_id}/media/{digest})"

    return _IMAGE.sub(replace, markdown)
