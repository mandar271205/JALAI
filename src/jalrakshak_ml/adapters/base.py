from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WeatherAdapter(ABC):
    """Source-specific adapter boundary.

    A source adapter may download/read its native format, but it should not leak
    source-specific assumptions into the rest of the pipeline.
    """

    source_name: str

    @abstractmethod
    def fetch(self, **kwargs: Any):
        raise NotImplementedError
