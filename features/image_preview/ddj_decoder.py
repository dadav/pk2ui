"""DDJ (Joymax/Silkroad) image format decoder.

DDJ is a proprietary container format that wraps DDS image data with a 20-byte header.
"""


DDJ_MAGIC = b"JMXVDDJ 1"
DDJ_HEADER_SIZE = 20


class DDJDecodeError(Exception):
    """Error decoding DDJ file."""

    pass


def decode_ddj(data: bytes) -> bytes:
    """Strip DDJ header and return underlying DDS data.

    DDJ Format:
        Offset  Size  Content
        0       9     "JMXVDDJ 1" magic header
        9       3     Padding (0x30 x3)
        12      4     File size - 1 (big-endian)
        16      4     Constant (0x03000000)
        20      ...   DDS image data

    Args:
        data: Raw DDJ file bytes

    Returns:
        DDS file bytes (header stripped)

    Raises:
        DDJDecodeError: If the file is not a valid DDJ
    """
    if len(data) < DDJ_HEADER_SIZE:
        raise DDJDecodeError("DDJ file too small")

    if data[:9] != DDJ_MAGIC:
        raise DDJDecodeError(f"Invalid DDJ magic: {data[:9]!r}")

    return data[DDJ_HEADER_SIZE:]


def is_ddj(data: bytes) -> bool:
    """Check if data appears to be a DDJ file.

    Args:
        data: File bytes to check

    Returns:
        True if file has DDJ magic header
    """
    return len(data) >= 9 and data[:9] == DDJ_MAGIC
