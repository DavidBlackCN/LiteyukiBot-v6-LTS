from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ImageQuery, ImageResult, ProviderCapabilities


class ImageProvider(ABC):
    name: str
    capabilities: ProviderCapabilities
    safe_available: bool = True

    def supports(self, query: ImageQuery) -> bool:
        c = self.capabilities
        return not ((query.keyword and not c.keyword) or (query.tags and not c.tags)
                    or (query.uid and not c.uid) or (query.pid and not c.pid)
                    or (query.author and not c.author) or (query.orientation and not c.orientation)
                    or ("exclude_ai" in query.explicit_filters and query.exclude_ai and not c.exclude_ai)
                    or ("size" in query.explicit_filters and query.size and not c.size)
                    or (query.r18 and not c.r18))

    @abstractmethod
    async def fetch(self, query: ImageQuery) -> list[ImageResult]:
        raise NotImplementedError
