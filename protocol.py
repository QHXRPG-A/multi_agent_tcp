import json
import struct
from typing import Any, Dict

_HEADER_STRUCT = struct.Struct("!I")  # big-endian uint32 length


def encode_frame(obj: Dict[str, Any]) -> bytes:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > 0xFFF_FFFF:
        raise ValueError("message too large")
    return _HEADER_STRUCT.pack(len(body)) + body


async def read_frame(reader) -> Dict[str, Any]:
    header = await reader.readexactly(_HEADER_STRUCT.size)
    (n,) = _HEADER_STRUCT.unpack(header)
    body = await reader.readexactly(n)
    return json.loads(body.decode("utf-8"))


async def write_frame(writer, obj: Dict[str, Any]) -> None:
    writer.write(encode_frame(obj))
    await writer.drain()

