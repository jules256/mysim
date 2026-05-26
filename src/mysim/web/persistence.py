"""Utility for encoding and decoding AppConfig as a URL-safe string."""

import base64
import zlib
import json
from decimal import Decimal
from typing import Any

from mysim.config import AppConfig


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def encode_config(config: AppConfig) -> str:
    """Serialize AppConfig to a zlib-compressed, base64-encoded string."""
    # Convert to dict, then to JSON string with Decimals as strings
    data = config.model_dump()
    json_str = json.dumps(data, cls=DecimalEncoder)

    # Compress and encode
    compressed = zlib.compress(json_str.encode("utf-8"))
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
    return encoded


def decode_config(encoded: str) -> AppConfig:
    """Decode a zlib-compressed, base64-encoded string back to AppConfig."""
    try:
        compressed = base64.urlsafe_b64decode(encoded)
        json_str = zlib.decompress(compressed).decode("utf-8")
        data = json.loads(json_str)
        return AppConfig(**data)
    except Exception as e:
        raise ValueError(f"Failed to decode configuration: {e}")
