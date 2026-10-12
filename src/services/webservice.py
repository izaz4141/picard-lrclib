from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from picard.plugin3.api import Album, PluginApi
from picard.webservice import PendingRequest

from ..common import constants


def request(
    api: PluginApi,
    url: str,
    album: Album,
    task_id: str,
    callback: Callable[..., None],
    queryargs: dict[str, Any] | None = None,
    important: bool = False,
    blocking: bool = False,
    timeout: float | None = None,
) -> None:
    """Queue an LRCLIB HTTP request as an album task."""
    if not queryargs:
        queryargs = {}

    def create_request() -> PendingRequest:
        """Create the pending request for the album task."""
        return api.web_service.get_url(
            url=url,
            handler=callback,
            parse_response_type="json",
            priority=True,
            important=important,
            queryargs=queryargs,
        )

    api.add_album_task(
        album,
        task_id,
        "Fetching data",
        timeout=timeout,
        request_factory=create_request,
        blocking=blocking,
    )


def search_refresh(
    api: PluginApi,
    album: Album,
    query: str,
    on_done: Callable[[Any, Any, Exception | None], None],
) -> None:
    """Issue a non-blocking LRCLIB search through Picard's web service."""
    task_id = f"search_refresh_{album.id}_{uuid.uuid4().hex[:8]}"

    def handler(response: Any, reply: Any, error: Exception | None) -> None:
        """Forward the response to the callback and finish the task."""
        try:
            on_done(response, reply, error)
        finally:
            api.complete_album_task(album, task_id)

    request(
        api,
        constants.lrclib_search_url,
        album,
        task_id,
        handler,
        {"q": query},
    )
