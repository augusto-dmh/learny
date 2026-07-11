"""EPUB ingestion adapters (ADR-0009, design §Components).

The only place ebooklib and BeautifulSoup are imported: the structure-preserving
parser (:mod:`app.infrastructure.ingestion.epub`) and the Markdown converter
(:mod:`app.infrastructure.ingestion.markup`) sit behind the domain ports so their
types never cross into ``domain`` or ``application`` contracts.
"""

from __future__ import annotations
