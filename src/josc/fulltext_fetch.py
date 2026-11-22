"""Fetch the open-access full text of a resolved paper.

Resolution reuses the provider lookup the aggregator already performs, then
downloads the best open-access PDF and extracts its text. A paywalled record
reports ``no_oa`` instead of an empty string, and a failed download or a
missing ``pypdf`` reports ``error``. The one non-OA route, Sci-Net, is opt-in
(see :mod:`josc.scinet`) and always labelled ``pdf_source="scinet"``.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from . import pdf_links
from . import scinet as scinet_client
from .config import get_scinet_enabled
from .models import Paper, ProviderError
from .pdf_text import extract_pdf_text_from_bytes
from .providers.base import ProviderBase

DEFAULT_MAX_CHARS = 20_000
ARXIV_PDF_URL = "https://arxiv.org/pdf/{id}"



def _nejm_ai_doi(doi: str) -> str:
    # DOIs are case-insensitive but ai.nejm.org paths are not: the journal's
    # suffixes are spelled ``AIdbp2500144`` / ``AIoa...``, so restore the "AI".
    prefix, suffix = doi.split("/", 1)
    return f"{prefix}/AI{suffix[2:]}"


def _peerj_article(doi: str) -> str:
    # 10.7717/peerj-cs.906 -> cs-906, 10.7717/peerj.1000 -> 1000
    suffix = doi.split("/", 1)[1].lower()
    journal, _, number = suffix.rpartition(".")
    journal = journal[len("peerj"):].lstrip("-")
    return f"{journal}-{number}" if journal else number


# Publisher download endpoints, tried after the record's own OA link and arXiv,
# as ``(source, DOI pattern, URL template, DOI rewrite)``. ACM's Digital
# Library is open access, and ``?download=true`` serves the PDF itself rather
# than the reader UI. NEJM AI articles live under ``10.1056/AI...``; PeerJ
# serves ``/articles/<journal>-<number>.pdf`` for ``10.7717/peerj-<journal>.<n>``.
PUBLISHER_PDF_ROUTES: List[Tuple[str, "re.Pattern[str]", str, Any]] = [
    (
        "acm",
        re.compile(r"^10\.1145/", re.I),
        "https://dl.acm.org/doi/pdf/{doi}?download=true",
        None,
    ),
    (
        "nejm_ai",
        re.compile(r"^10\.1056/ai", re.I),
        "https://ai.nejm.org/doi/pdf/{doi}",
        _nejm_ai_doi,
    ),
    (
        "peerj",
        re.compile(r"^10\.7717/peerj(-[a-z]+)?\.\d+$", re.I),
        "https://peerj.com/articles/{doi}.pdf",
        _peerj_article,
    ),
]
PUBLISHER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*;q=0.8",
}


async def _resolve(providers: List[ProviderBase], identifier: str) -> Optional[Paper]:
    """Ask every lookup-capable provider for the identifier, first hit wins."""
    candidates = [
        provider
        for provider in providers
        if not provider.enricher and getattr(provider, "get", None) is not None
    ]
    if not candidates:
        return None
    outcomes = await asyncio.gather(
        *(provider.get(identifier) for provider in candidates),
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, Paper):
            return outcome
    return None


async def _attach_oa_links(providers: List[ProviderBase], paper: Paper) -> Paper:
    """Ask the enrichers for a better open-access PDF link.

    Mirrors the aggregator's enrichment pass, but stops at the first link so
    a paywalled record is not silently re-checked against every enricher.
    Errors are swallowed: enrichment is best-effort, a failure there must not
    block a PDF the primary source already resolved.
    """
    if paper.pdf_url or not paper.doi:
        return paper
    for provider in providers:
        if not provider.enricher:
            continue
        try:
            extra = await provider.get(paper.doi)
        except ProviderError:
            continue
        if extra and extra.pdf_url:
            paper.pdf_url = extra.pdf_url
            if extra.is_open_access is not None:
                paper.is_open_access = extra.is_open_access
            break
    return paper


def _oa_candidates(paper: Paper) -> List[Tuple[str, str]]:
    """Open-access PDF links worth trying, best first, as ``(source, url)``."""
    candidates: List[Tuple[str, str]] = []
    if paper.pdf_url:
        candidates.append(("open_access", paper.pdf_url))
    arxiv_id = (paper.ids or {}).get("arxiv")
    if arxiv_id:
        arxiv_url = ARXIV_PDF_URL.format(id=arxiv_id)
        if arxiv_url != paper.pdf_url:
            candidates.append(("arxiv", arxiv_url))
    return candidates


def _publisher_candidate(doi: Optional[str]) -> Optional[Tuple[str, str]]:
    """The publisher's own PDF endpoint for ``doi``, when one is known."""
    bare = scinet_client.normalize_doi(doi)
    if not bare:
        return None
    for source, pattern, template, rewrite in PUBLISHER_PDF_ROUTES:
        if pattern.match(bare):
            return source, template.format(doi=rewrite(bare) if rewrite else bare)
    return None


def _fetcher(providers: List[ProviderBase], paper: Optional[Paper] = None) -> Any:
    for provider in providers:
        if getattr(provider, "fetcher", None) is not None:
            return provider.fetcher
    return None


def _looks_like_pdf(data: bytes) -> bool:
    # Publishers often answer a "PDF" link with an HTML landing page or a bot
    # challenge; pypdf would then fail with an opaque parse error.
    return isinstance(data, (bytes, bytearray)) and b"%PDF-" in bytes(data[:1024])


async def _download_text(
    fetcher: Any, url: str, headers: Optional[Dict[str, str]] = None
) -> str:
    """Download ``url`` and extract its text; raise ``ValueError`` on non-PDFs.

    Redirects are followed: PDF links routinely bounce through a CDN or an
    ``/pdf`` -> ``/pdf/<file>`` hop before the bytes arrive.
    """
    kwargs: Dict[str, Any] = {"provider": "fulltext", "follow_redirects": True}
    if headers:
        kwargs["headers"] = headers
    data = await fetcher.get_bytes(url, **kwargs)
    if not _looks_like_pdf(data):
        raise ValueError(f"{url} did not return a PDF (landing page or bot challenge?)")
    return extract_pdf_text_from_bytes(data)


def _result(identifier: str, status: str, **fields: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "identifier": identifier,
        "status": status,
        "full_text": None,
        "pdf_url": None,
        "truncated": False,
    }
    payload.update(fields)
    return payload


async def fetch_fulltext(
    providers: List[ProviderBase],
    identifier: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    scinet: Optional[bool] = None,
) -> Dict[str, Any]:
    """Resolve ``identifier`` to a PDF and return its extracted text.

    Routes are tried in order, each only when every earlier one failed (HTTP
    error, non-PDF reply, or nothing to try):

    1. ``open_access`` / ``arxiv``: the record's own PDF link, then arXiv.
    2. ``crossref``: ``application/pdf`` links the publisher deposited.
    3. ``landing``: ``citation_pdf_url`` on the page ``doi.org`` redirects to.
    4. ``acm`` / ``nejm_ai`` / ``peerj``: hard-coded ``PUBLISHER_PDF_ROUTES``.
    5. ``scinet``: only when enabled (``None`` reads
       :func:`josc.config.get_scinet_enabled`).

    ``pdf_source`` names the route that produced the text; ``attempts`` lists
    the ones that failed before it.
    """
    use_scinet = get_scinet_enabled() if scinet is None else scinet
    paper = await _resolve(providers, identifier)
    resolved = paper is not None
    if paper is None:
        bare_doi = scinet_client.normalize_doi(identifier)
        if not bare_doi:
            return _result(identifier, "not_found")
        # No metadata source knows it, but every DOI route below needs only
        # the DOI itself.
        paper = Paper(doi=bare_doi)
    else:
        await _attach_oa_links(providers, paper)

    fetcher = _fetcher(providers, paper)
    doi = scinet_client.normalize_doi(paper.doi)
    if fetcher is None or not hasattr(fetcher, "get_bytes"):
        static = _oa_candidates(paper)
        publisher = _publisher_candidate(doi)
        if publisher:
            static.append(publisher)
        if not static:
            return _result(identifier, "no_oa" if resolved else "not_found")
        return _result(
            identifier,
            "error",
            pdf_url=static[0][1],
            error="No fetcher available to download the PDF.",
            paper=paper.to_dict(),
        )

    async def _crossref() -> List[Tuple[str, str]]:
        urls = await pdf_links.find_crossref_pdf_links(fetcher, doi) if doi else []
        return [("crossref", url) for url in urls]

    async def _landing() -> List[Tuple[str, str]]:
        urls = await pdf_links.find_landing_pdf_links(fetcher, doi) if doi else []
        return [("landing", url) for url in urls]

    async def _publisher() -> List[Tuple[str, str]]:
        route = _publisher_candidate(doi)
        return [route] if route else []

    async def _scinet() -> List[Tuple[str, str]]:
        if not (use_scinet and doi):
            return []
        url = await scinet_client.find_pdf_url(fetcher, doi)
        return [("scinet", url)] if url else []

    async def _own() -> List[Tuple[str, str]]:
        return _oa_candidates(paper)

    attempts: List[Dict[str, str]] = []
    tried: set = set()

    async def _try(source: str, url: str) -> Optional[str]:
        # The record's own links keep the default client headers; publisher
        # pages get a browser-like UA, which their front ends expect.
        headers = None if source in ("open_access", "arxiv") else PUBLISHER_HEADERS
        try:
            return await _download_text(fetcher, url, headers)
        except ProviderError as exc:
            attempts.append({"source": source, "pdf_url": url, "error": exc.message})
        except Exception as exc:  # pypdf missing, malformed PDF, HTML page, ...
            attempts.append({"source": source, "pdf_url": url, "error": str(exc)})
        return None

    text: Optional[str] = None
    source = pdf_url = None
    for stage in (_own, _crossref, _landing, _publisher, _scinet):
        for source, pdf_url in await stage():
            if pdf_url in tried:
                continue
            tried.add(pdf_url)
            text = await _try(source, pdf_url)
            if text is not None:
                break
        if text is not None:
            break

    if text is None:
        extra: Dict[str, Any] = {"paper": paper.to_dict()}
        if not attempts:
            return _result(identifier, "no_oa" if resolved else "not_found", **extra)
        last = attempts[-1]
        if len(attempts) > 1:
            extra["attempts"] = attempts
        return _result(
            identifier, "error", pdf_url=last["pdf_url"], error=last["error"], **extra
        )

    truncated = len(text) > max_chars
    payload = _result(
        identifier,
        "found",
        full_text=text[:max_chars],
        pdf_url=pdf_url,
        pdf_source=source,
        truncated=truncated,
        chars=min(len(text), max_chars),
        paper=paper.to_dict(),
    )
    if attempts:
        payload["attempts"] = attempts
    return payload
