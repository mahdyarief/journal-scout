from datetime import datetime
from typing import Any, List, Optional

from ..exa_client import call_exa_mcp
from ..models import Paper
from ..utils import parse_year
from .base import ProviderBase


class ExaProvider(ProviderBase):
    """Search the web for papers using Exa's MCP search tool."""

    name = "exa"
    supports_search = True

    @staticmethod
    def _results(payload: Any) -> List[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "papers", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_paper(item: dict) -> Optional[Paper]:
        title = (item.get("title") or "").strip()
        url = item.get("url") or item.get("link")
        if not title:
            return None

        published = item.get("publishedDate") or item.get("published_date") or item.get("date")
        year = parse_year(published)
        if year is None and isinstance(published, str):
            try:
                year = datetime.fromisoformat(published.replace("Z", "+00:00")).year
            except ValueError:
                pass

        author = item.get("author")
        authors = item.get("authors") or ([author] if isinstance(author, str) else [])
        authors = [name.strip() for name in authors if isinstance(name, str) and name.strip()]
        abstract = item.get("text") or item.get("summary") or item.get("snippet")
        return Paper(
            title=title,
            abstract=abstract,
            year=year,
            authors=authors,
            url=url,
            pdf_url=item.get("pdf_url") or item.get("pdfUrl"),
            sources=["exa"],
            ids={"exa": str(url)} if url else {},
        )

    async def search(
        self,
        query: str,
        limit: int,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        tech_only: bool = False,
        offset: int = 0,
        **_: object,
    ) -> List[Paper]:
        del year_from, year_to, tech_only, offset
        payload = await call_exa_mcp(
            "web_search_exa",
            {
                "query": query,
                "numResults": max(1, min(100, limit)),
                "livecrawl": "fallback",
                "type": "auto",
            },
        )
        return [
            paper
            for item in self._results(payload)
            if (paper := self._to_paper(item)) is not None
        ][:limit]
