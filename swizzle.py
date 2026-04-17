# Nintendo Switch GOB swizzle/deswizzle
# Derived from Aclios/pyswizzle (MIT License)

import numpy as np


def nsw_swizzle(data, im_size, block_size, bytes_per_block, swizzle_mode):
    return _BytesSwizzle(data, im_size, block_size, bytes_per_block, swizzle_mode).swizzle()


def nsw_deswizzle(data, im_size, block_size, bytes_per_block, swizzle_mode):
    return _BytesDeswizzle(data, im_size, block_size, bytes_per_block, swizzle_mode).deswizzle()


class _BytesSwizzle:
    def __init__(self, data, im_size, block_size, bytes_per_block, swizzle_mode):
        self.data = data
        datasize = len(data)
        im_width, im_height = im_size
        block_width, block_height = block_size

        expected = (im_width * im_height) // (block_width * block_height) * bytes_per_block
        if expected != datasize:
            raise ValueError(f"Invalid data size: expected {expected}, got {datasize}")

        tile_datasize = 512 * (2 ** swizzle_mode)
        tile_width = 64 // bytes_per_block * block_width
        tile_height = 8 * block_height * (2 ** swizzle_mode)

        if datasize % tile_datasize != 0:
            raise ValueError(f"Data size must be a multiple of {tile_datasize}")
        if im_width % tile_width != 0:
            raise ValueError(f"Image width must be a multiple of {tile_width}")
        if im_height % tile_height != 0:
            raise ValueError(f"Image height must be a multiple of {tile_height}")

        self.swizzle_ops = [(2 ** swizzle_mode, 0), (2, 1), (4, 0), (2, 1), (2, 0)]
        self.read_size = 16
        self.column_count = (bytes_per_block * im_width) // (block_width * 16)
        self.tile_per_width = im_width // tile_width
        self.tile_per_height = im_height // tile_height
        self.row_count = im_height // block_height

    def _to_array(self):
        idx = 0
        array = None
        for i in range(self.row_count):
            row = []
            for _ in range(self.column_count):
                row.append(self.data[idx: idx + self.read_size])
                idx += self.read_size
            arr_row = np.array([row], dtype=np.void)
            array = arr_row if array is None else np.vstack((array, arr_row))
        return array

    @staticmethod
    def _split(arrays, n, axis):
        result = []
        for a in arrays:
            result.extend(np.split(a, n, axis))
        return result

    def swizzle(self):
        out = bytearray()
        tiles = self._split([self._to_array()], self.tile_per_height, 0)
        tiles = self._split(tiles, self.tile_per_width, 1)
        for tile in tiles:
            parts = [tile]
            for n, axis in self.swizzle_ops:
                parts = self._split(parts, n, axis)
            for block in parts:
                out += block[0][0].item()
        return bytes(out)


class _BytesDeswizzle:
    def __init__(self, data, im_size, block_size, bytes_per_block, swizzle_mode):
        self.data = data
        datasize = len(data)
        im_width, im_height = im_size
        block_width, block_height = block_size

        expected = (im_width * im_height) // (block_width * block_height) * bytes_per_block
        if expected != datasize:
            raise ValueError(f"Invalid data size: expected {expected}, got {datasize}")

        tile_datasize = 512 * (2 ** swizzle_mode)
        tile_width = 64 // bytes_per_block * block_width
        tile_height = 8 * block_height * (2 ** swizzle_mode)

        self.deswizzle_ops = [(2, 0), (2, 1), (4, 0), (2, 1), (2 ** swizzle_mode, 0)]
        self.read_size = 16
        self.read_per_tile = 32 * (2 ** swizzle_mode)
        self.tile_count = datasize // tile_datasize
        self.tile_per_width = im_width // tile_width
        self.data_idx = 0

    def _read_tile(self):
        parts = []
        for _ in range(self.read_per_tile):
            parts.append(np.array([[self.data[self.data_idx: self.data_idx + self.read_size]]], dtype=np.void))
            self.data_idx += self.read_size
        return parts

    @staticmethod
    def _concat(arrays, n, axis):
        result = []
        for i in range(0, len(arrays), n):
            result.append(np.concatenate(arrays[i: i + n], axis=axis))
        return result

    def _deswizzle_tile(self):
        parts = self._read_tile()
        for n, axis in self.deswizzle_ops:
            parts = self._concat(parts, n, axis)
        return parts[0]

    def deswizzle(self):
        tiles = [self._deswizzle_tile() for _ in range(self.tile_count)]
        rows = self._concat(tiles, self.tile_per_width, 1)
        full = self._concat(rows, len(rows), 0)[0]
        return full.tobytes()
