"""Persistence utility for encoding/decoding AppConfig into URL parameters."""

from __future__ import annotations

import base64
import json
import zlib
from decimal import Decimal
from typing import Any

from mysim.config import AppConfig


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def encode_config(config: AppConfig) -> str:
    """Serialize, compress, and base64-encode an AppConfig."""
    # Convert to dict, then JSON
    data = config.model_dump()
    # Use a compact JSON representation
    json_str = json.dumps(data, separators=(",", ":"), cls=DecimalEncoder)
    # Compress
    compressed = zlib.compress(json_str.encode("utf-8"))
    # Base64 encode (using urlsafe variant)
    return base64.urlsafe_b64encode(compressed).decode("utf-8")


def decode_config(encoded: str) -> AppConfig:
    """Decode, decompress, and deserialize an AppConfig from a base64 string."""
    # Base64 decode
    compressed = base64.urlsafe_b64decode(encoded.encode("utf-8"))
    # Decompress
    json_str = zlib.decompress(compressed).decode("utf-8")
    # Deserialize
    data = json.loads(json_str)
    return AppConfig(**data)
