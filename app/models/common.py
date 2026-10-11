"""Shared view-model pieces."""

from math import ceil
from typing import Literal

from pydantic import BaseModel

PAGE_SIZE = 25

# Source label shown on every record.
SourceLabel = Literal["EMR", "EMR history", "PM", "Pre-2010"]


class Pager(BaseModel):
    page: int
    total: int
    page_size: int = PAGE_SIZE

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.page_size))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def shown(self) -> int:
        """Number of rows on the current page."""
        return max(0, min(self.page_size, self.total - self.offset))


def clamp_page(page: int | None) -> int:
    return page if page and page > 0 else 1


def paginate[T](items: list[T], page: int, page_size: int = PAGE_SIZE) -> tuple[list[T], Pager]:
    """Slice an in-memory list (fake data / merged lists) into one page."""
    pager = Pager(page=clamp_page(page), total=len(items), page_size=page_size)
    if pager.page > pager.pages:
        pager = Pager(page=pager.pages, total=len(items), page_size=page_size)
    return items[pager.offset : pager.offset + page_size], pager
