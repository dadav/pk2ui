"""DDS (DirectDraw Surface) decoder for PyQt6.

Supports DXT1, DXT3, DXT5 compressed formats and uncompressed RGBA/RGB.
"""

import struct
from typing import Optional

from PyQt6.QtGui import QImage


# DDS file format constants
DDS_MAGIC = b"DDS "
DDS_HEADER_SIZE = 124

# Pixel format flags
DDPF_ALPHAPIXELS = 0x1
DDPF_FOURCC = 0x4
DDPF_RGB = 0x40

# FourCC codes
FOURCC_DXT1 = b"DXT1"
FOURCC_DXT3 = b"DXT3"
FOURCC_DXT5 = b"DXT5"


class DDSDecodeError(Exception):
    """Error decoding DDS file."""

    pass


def decode_dds(data: bytes) -> QImage:
    """Decode DDS image data to QImage.

    Args:
        data: Raw DDS file bytes

    Returns:
        QImage with decoded image

    Raises:
        DDSDecodeError: If decoding fails
    """
    if len(data) < 128:
        raise DDSDecodeError("DDS file too small")

    # Check magic
    if data[:4] != DDS_MAGIC:
        raise DDSDecodeError("Invalid DDS magic")

    # Parse header
    header_size = struct.unpack_from("<I", data, 4)[0]
    if header_size != DDS_HEADER_SIZE:
        raise DDSDecodeError(f"Invalid DDS header size: {header_size}")

    # Extract dimensions
    height = struct.unpack_from("<I", data, 12)[0]
    width = struct.unpack_from("<I", data, 16)[0]

    # Parse pixel format (starts at offset 76)
    pf_size = struct.unpack_from("<I", data, 76)[0]
    pf_flags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    rgb_bit_count = struct.unpack_from("<I", data, 88)[0]
    r_mask = struct.unpack_from("<I", data, 92)[0]
    g_mask = struct.unpack_from("<I", data, 96)[0]
    b_mask = struct.unpack_from("<I", data, 100)[0]
    a_mask = struct.unpack_from("<I", data, 104)[0]

    # Image data starts after header (128 bytes)
    image_data = data[128:]

    if pf_flags & DDPF_FOURCC:
        # Compressed format
        if fourcc == FOURCC_DXT1:
            rgba = _decode_dxt1(image_data, width, height)
        elif fourcc == FOURCC_DXT3:
            rgba = _decode_dxt3(image_data, width, height)
        elif fourcc == FOURCC_DXT5:
            rgba = _decode_dxt5(image_data, width, height)
        else:
            raise DDSDecodeError(f"Unsupported FourCC: {fourcc}")
    elif pf_flags & DDPF_RGB:
        # Uncompressed format
        rgba = _decode_uncompressed(
            image_data, width, height, rgb_bit_count, r_mask, g_mask, b_mask, a_mask
        )
    else:
        raise DDSDecodeError(f"Unsupported pixel format flags: {pf_flags:#x}")

    # Create QImage from RGBA data
    image = QImage(rgba, width, height, width * 4, QImage.Format.Format_RGBA8888)
    # Return a copy since QImage doesn't take ownership of the data
    return image.copy()


def _decode_dxt1(data: bytes, width: int, height: int) -> bytes:
    """Decode DXT1 (BC1) compressed data."""
    output = bytearray(width * height * 4)

    block_width = (width + 3) // 4
    block_height = (height + 3) // 4
    offset = 0

    for by in range(block_height):
        for bx in range(block_width):
            if offset + 8 > len(data):
                break

            # Read block (8 bytes)
            c0 = struct.unpack_from("<H", data, offset)[0]
            c1 = struct.unpack_from("<H", data, offset + 2)[0]
            indices = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8

            # Decode colors from RGB565
            colors = [_rgb565_to_rgba(c0), _rgb565_to_rgba(c1), None, None]

            if c0 > c1:
                # 4-color block (opaque)
                colors[2] = _interpolate_color(colors[0], colors[1], 1, 3)
                colors[3] = _interpolate_color(colors[0], colors[1], 2, 3)
            else:
                # 3-color block with transparency
                colors[2] = _interpolate_color(colors[0], colors[1], 1, 2)
                colors[3] = (0, 0, 0, 0)  # Transparent

            # Fill pixels
            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x < width and y < height:
                        idx = (indices >> (2 * (py * 4 + px))) & 0x3
                        color = colors[idx]
                        pos = (y * width + x) * 4
                        output[pos : pos + 4] = bytes(color)

    return bytes(output)


def _decode_dxt3(data: bytes, width: int, height: int) -> bytes:
    """Decode DXT3 (BC2) compressed data."""
    output = bytearray(width * height * 4)

    block_width = (width + 3) // 4
    block_height = (height + 3) // 4
    offset = 0

    for by in range(block_height):
        for bx in range(block_width):
            if offset + 16 > len(data):
                break

            # Read alpha (8 bytes - 4-bit per pixel)
            alpha_data = data[offset : offset + 8]
            offset += 8

            # Read color block (8 bytes)
            c0 = struct.unpack_from("<H", data, offset)[0]
            c1 = struct.unpack_from("<H", data, offset + 2)[0]
            indices = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8

            # Decode colors
            colors = [
                _rgb565_to_rgba(c0)[:3],
                _rgb565_to_rgba(c1)[:3],
                None,
                None,
            ]
            colors[2] = _interpolate_color_rgb(colors[0], colors[1], 1, 3)
            colors[3] = _interpolate_color_rgb(colors[0], colors[1], 2, 3)

            # Fill pixels
            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x < width and y < height:
                        # Get alpha (4-bit)
                        alpha_byte_idx = py * 2 + px // 2
                        if px % 2 == 0:
                            alpha = (alpha_data[alpha_byte_idx] & 0x0F) * 17
                        else:
                            alpha = ((alpha_data[alpha_byte_idx] >> 4) & 0x0F) * 17

                        # Get color
                        idx = (indices >> (2 * (py * 4 + px))) & 0x3
                        color = colors[idx]

                        pos = (y * width + x) * 4
                        output[pos] = color[0]
                        output[pos + 1] = color[1]
                        output[pos + 2] = color[2]
                        output[pos + 3] = alpha

    return bytes(output)


def _decode_dxt5(data: bytes, width: int, height: int) -> bytes:
    """Decode DXT5 (BC3) compressed data."""
    output = bytearray(width * height * 4)

    block_width = (width + 3) // 4
    block_height = (height + 3) // 4
    offset = 0

    for by in range(block_height):
        for bx in range(block_width):
            if offset + 16 > len(data):
                break

            # Read alpha block (8 bytes)
            a0 = data[offset]
            a1 = data[offset + 1]
            alpha_indices = (
                struct.unpack_from("<I", data, offset + 2)[0]
                | (struct.unpack_from("<H", data, offset + 6)[0] << 32)
            )
            offset += 8

            # Calculate alpha lookup table
            alphas = [a0, a1, 0, 0, 0, 0, 0, 0]
            if a0 > a1:
                for i in range(6):
                    alphas[i + 2] = ((6 - i) * a0 + (i + 1) * a1) // 7
            else:
                for i in range(4):
                    alphas[i + 2] = ((4 - i) * a0 + (i + 1) * a1) // 5
                alphas[6] = 0
                alphas[7] = 255

            # Read color block (8 bytes)
            c0 = struct.unpack_from("<H", data, offset)[0]
            c1 = struct.unpack_from("<H", data, offset + 2)[0]
            indices = struct.unpack_from("<I", data, offset + 4)[0]
            offset += 8

            # Decode colors
            colors = [
                _rgb565_to_rgba(c0)[:3],
                _rgb565_to_rgba(c1)[:3],
                None,
                None,
            ]
            colors[2] = _interpolate_color_rgb(colors[0], colors[1], 1, 3)
            colors[3] = _interpolate_color_rgb(colors[0], colors[1], 2, 3)

            # Fill pixels
            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x < width and y < height:
                        # Get alpha (3-bit index)
                        alpha_bit_offset = (py * 4 + px) * 3
                        alpha_idx = (alpha_indices >> alpha_bit_offset) & 0x7
                        alpha = alphas[alpha_idx]

                        # Get color
                        idx = (indices >> (2 * (py * 4 + px))) & 0x3
                        color = colors[idx]

                        pos = (y * width + x) * 4
                        output[pos] = color[0]
                        output[pos + 1] = color[1]
                        output[pos + 2] = color[2]
                        output[pos + 3] = alpha

    return bytes(output)


def _decode_uncompressed(
    data: bytes,
    width: int,
    height: int,
    bit_count: int,
    r_mask: int,
    g_mask: int,
    b_mask: int,
    a_mask: int,
) -> bytes:
    """Decode uncompressed RGB/RGBA data."""
    output = bytearray(width * height * 4)
    bytes_per_pixel = bit_count // 8

    # Calculate shift and scale for each channel
    def get_shift_scale(mask: int) -> tuple[int, int]:
        if mask == 0:
            return 0, 0
        shift = 0
        while (mask >> shift) & 1 == 0:
            shift += 1
        bits = 0
        temp = mask >> shift
        while temp & 1:
            bits += 1
            temp >>= 1
        scale = 255 // ((1 << bits) - 1) if bits > 0 else 0
        return shift, scale

    r_shift, r_scale = get_shift_scale(r_mask)
    g_shift, g_scale = get_shift_scale(g_mask)
    b_shift, b_scale = get_shift_scale(b_mask)
    a_shift, a_scale = get_shift_scale(a_mask)

    offset = 0
    for y in range(height):
        for x in range(width):
            if offset + bytes_per_pixel > len(data):
                break

            # Read pixel value
            if bytes_per_pixel == 4:
                pixel = struct.unpack_from("<I", data, offset)[0]
            elif bytes_per_pixel == 3:
                pixel = data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)
            elif bytes_per_pixel == 2:
                pixel = struct.unpack_from("<H", data, offset)[0]
            else:
                pixel = data[offset]
            offset += bytes_per_pixel

            # Extract channels
            r = ((pixel & r_mask) >> r_shift) * r_scale if r_mask else 0
            g = ((pixel & g_mask) >> g_shift) * g_scale if g_mask else 0
            b = ((pixel & b_mask) >> b_shift) * b_scale if b_mask else 0
            a = ((pixel & a_mask) >> a_shift) * a_scale if a_mask else 255

            pos = (y * width + x) * 4
            output[pos] = min(255, max(0, r))
            output[pos + 1] = min(255, max(0, g))
            output[pos + 2] = min(255, max(0, b))
            output[pos + 3] = min(255, max(0, a))

    return bytes(output)


def _rgb565_to_rgba(color: int) -> tuple[int, int, int, int]:
    """Convert RGB565 to RGBA8888."""
    r = ((color >> 11) & 0x1F) * 255 // 31
    g = ((color >> 5) & 0x3F) * 255 // 63
    b = (color & 0x1F) * 255 // 31
    return (r, g, b, 255)


def _interpolate_color(
    c0: tuple[int, int, int, int], c1: tuple[int, int, int, int], num: int, denom: int
) -> tuple[int, int, int, int]:
    """Interpolate between two colors."""
    inv = denom - num
    return (
        (c0[0] * inv + c1[0] * num) // denom,
        (c0[1] * inv + c1[1] * num) // denom,
        (c0[2] * inv + c1[2] * num) // denom,
        255,
    )


def _interpolate_color_rgb(
    c0: tuple[int, int, int], c1: tuple[int, int, int], num: int, denom: int
) -> tuple[int, int, int]:
    """Interpolate between two RGB colors."""
    inv = denom - num
    return (
        (c0[0] * inv + c1[0] * num) // denom,
        (c0[1] * inv + c1[1] * num) // denom,
        (c0[2] * inv + c1[2] * num) // denom,
    )
