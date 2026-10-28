"""Posts domain helpers."""

from src.posts.constants import PostStatus


def is_editable(status: str | PostStatus) -> bool:
    """Archived posts are immutable."""
    value = status.value if isinstance(status, PostStatus) else status
    return value != PostStatus.ARCHIVED.value
