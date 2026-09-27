# -*- coding: utf-8 -*-
"""Optional Numba implementation of the Mandelbrot escape-time kernel.

This module is deliberately imported lazily by :mod:`.model`.  NumPy remains
the required, zero-setup backend; importing the rest of prismath therefore
does not import Numba or pay its startup cost.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np

__all__ = ["escape_counts_numba", "interior_mask_numba"]


try:  # The module itself is loaded only when the caller requests Numba.
    import numba as _numba
except ImportError as exc:  # pragma: no cover - tested in a subprocess without Numba
    raise ImportError(
        "Numba 后端不可用：请安装兼容的可选依赖（`python -m pip install numba`），"
        "或选择 backend='numpy'。"
    ) from exc


@_numba.njit(cache=True, parallel=True, nogil=True)
def _interior_mask_kernel(real, imag, disks, big_disk, big_max_x):
    """与 model.interior_mask 同式；常量由模型传入，避免维护两份圆盘参数。"""
    mask = np.empty(real.size, dtype=np.bool_)
    for index in _numba.prange(real.size):
        x, y = real[index], imag[index]
        q = (x - 0.25) ** 2 + y * y
        inside = (q * (q + (x - 0.25)) <= 0.25 * y * y
                  or (x + 1.0) ** 2 + y * y <= 0.0625)
        for cx, cy, radius in disks:
            inside = inside or (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
        cx, cy, radius = big_disk
        mask[index] = inside or ((x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
                                 and x <= big_max_x)
    return mask


def interior_mask_numba(points, disks, big_disk, big_max_x):
    """编译的解析判据，减少大数组上的临时内存分配。"""
    real = np.ascontiguousarray(points.real.reshape(-1))
    imag = np.ascontiguousarray(points.imag.reshape(-1))
    return _interior_mask_kernel(
        real, imag, np.asarray(disks, dtype=np.float64),
        np.asarray(big_disk, dtype=np.float64), big_max_x,
    ).reshape(points.shape)


@_numba.njit(cache=True, parallel=True, nogil=True)
def _escape_counts_kernel(
    real_c: np.ndarray,
    imag_c: np.ndarray,
    interior: np.ndarray,
    max_iter: int,
    bailout2: float,
    log_bailout: float,
    inv_log2: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """每个像素独立迭代；不用 fastmath，保持与 NumPy 相同的运算顺序。

    内部掩码复用模型的解析判据。释放 GIL，使 Tk 的后台渲染不阻塞界面；
    编译结果缓存到磁盘，后续启动可复用（仍需导入和加载缓存）。
    """
    size = real_c.size
    counts = np.zeros(size, dtype=np.int32)
    smooth = np.full(size, float(max_iter), dtype=np.float64)
    for index in _numba.prange(size):
        if interior[index]:
            continue

        cr = real_c[index]
        ci = imag_c[index]
        zr = 0.0
        zi = 0.0
        for iteration in range(1, max_iter + 1):
            real2 = zr * zr
            imag2 = zi * zi
            zi = 2.0 * zr * zi + ci
            zr = real2 - imag2 + cr
            magnitude2 = zr * zr + zi * zi
            if magnitude2 > bailout2:
                counts[index] = iteration
                magnitude = math.sqrt(magnitude2)
                smooth[index] = (
                    (iteration + 1)
                    - math.log(math.log(magnitude) / log_bailout) * inv_log2
                )
                break
    return counts, smooth


def escape_counts_numba(
    real: np.ndarray,
    imag: np.ndarray,
    interior: np.ndarray,
    max_iter: int,
    bailout: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run the optional Numba kernel and return flat ``(counts, smooth)`` arrays."""

    real = np.ascontiguousarray(np.asarray(real, dtype=np.float64).reshape(-1))
    imag = np.ascontiguousarray(np.asarray(imag, dtype=np.float64).reshape(-1))
    interior = np.ascontiguousarray(np.asarray(interior, dtype=np.bool_).reshape(-1))
    if real.size != imag.size or real.size != interior.size:
        raise ValueError("Numba 后端的实部、虚部和内部掩码长度必须一致")

    # 参数已由 model.escape_counts 统一校正。
    return _escape_counts_kernel(
        real,
        imag,
        interior,
        max_iter,
        bailout * bailout,
        math.log(bailout),
        1.0 / math.log(2.0),
    )
