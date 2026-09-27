# -*- coding: utf-8 -*-
"""用傅里叶旋转矢量把一条二维曲线画出来。

把平面点 ``(x, y)`` 看成复数 ``z = x + i*y``。对按曲线顺序均匀采样的点
做离散傅里叶变换后，每个复系数就是一个旋转向量：模长是圆半径，辐角是初始
相位，整数频率决定旋转方向和速度。向量首尾相接时，最末端就是画笔位置。
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    "DEFAULT_SHAPE", "DEFAULT_SAMPLES", "DEFAULT_TERMS", "DEFAULT_FRAMES",
    "SHAPE_LABELS", "FourierResult", "FourierEpicycle", "sample_shape",
    "extract_image_contour",
    "dft_coefficients", "evaluate_series", "analyze_points",
]

DEFAULT_SHAPE = "heart"
DEFAULT_SAMPLES = 512
DEFAULT_TERMS = 31
DEFAULT_FRAMES = 360

MIN_SAMPLES = 64
MAX_SAMPLES = 2048
MIN_TERMS = 3
MAX_TERMS = 121
MIN_FRAMES = 60
# 允许更细的末端轨迹采样；默认值仍保持为 360，避免改变首次体验。
MAX_FRAMES = 36000

SHAPE_LABELS: Mapping[str, str] = {
    "heart": "心形",
    "star": "星形",
    "flower": "花瓣",
    "circle": "圆形",
    "lissajous": "李萨如曲线",
    "image": "图片轮廓",
    "sample_image": "示例图片轮廓",
}

_SAMPLE_CONTOUR_FILE = Path(__file__).with_name("assets") / "sample_image_contour.json"


def _finite_float(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return number if math.isfinite(number) else fallback


def _clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(low, min(high, number))


def _normalize_points(points: Any) -> np.ndarray:
    """转成居中的单位尺度复数轮廓，拒绝空点集和非有限输入。"""
    raw = np.asarray(points)
    if raw.ndim == 1 and np.iscomplexobj(raw):
        values = raw.astype(np.complex128, copy=False).reshape(-1)
    elif raw.ndim == 2 and raw.shape[1] >= 2:
        values = raw[:, 0].astype(float) + 1j * raw[:, 1].astype(float)
    else:
        raise ValueError("轮廓点必须是复数序列或形状为 (N, 2) 的坐标数组。")
    if values.size < 3 or not np.isfinite(values).all():
        raise ValueError("轮廓至少需要 3 个有限坐标点。")
    values = values - np.mean(values)
    scale = float(np.max(np.abs(values)))
    if scale <= np.finfo(float).eps:
        raise ValueError("轮廓不能退化为一个点。")
    return values / scale


def _as_rgb_array(image: Any) -> np.ndarray:
    """把数组或 Pillow 图像转成 ``uint8`` RGB。"""
    raw = np.asarray(image)
    if raw.ndim == 2:
        raw = np.repeat(raw[..., None], 3, axis=2)
    if raw.ndim != 3 or raw.shape[2] < 1:
        raise ValueError("图片必须是灰度图、RGB 或 RGBA 图像。")
    if raw.shape[2] == 1:
        raw = np.repeat(raw, 3, axis=2)
    elif raw.shape[2] > 3:
        raw = raw[..., :3]
    if np.issubdtype(raw.dtype, np.floating):
        scale = 255.0 if float(np.nanmax(raw)) <= 1.0 else 1.0
        raw = np.nan_to_num(raw, nan=0.0, posinf=255.0, neginf=0.0) * scale
    return np.clip(raw, 0, 255).astype(np.uint8, copy=False)


def _read_image(source: Any) -> np.ndarray:
    """读取图片；OpenCV 和 Pillow 都是可选依赖，数组输入无需额外依赖。"""
    if isinstance(source, np.ndarray):
        image = source
    else:
        path = Path(str(source)).expanduser()
        if not path.is_file():
            raise ValueError(f"找不到图片文件：{path}")
        image = None
        try:
            from PIL import Image  # type: ignore
            with Image.open(path) as opened:
                image = np.asarray(opened.convert("RGB"))
        except (ImportError, OSError, ValueError):
            try:
                import cv2  # type: ignore
                image = cv2.cvtColor(cv2.imread(str(path), cv2.IMREAD_COLOR),
                                     cv2.COLOR_BGR2RGB)
            except (ImportError, AttributeError, OSError, TypeError, ValueError):
                image = None
        if image is None:
            raise ValueError("无法读取图片；请安装 Pillow 或 opencv-python。")
    image = _as_rgb_array(image)
    height, width = image.shape[:2]
    if height < 8 or width < 8:
        raise ValueError("图片太小，至少需要 8×8 像素。")
    # 轮廓识别不需要保留原图分辨率，限制最大边可避免大图拖慢 Tk 首次绘制。
    max_side = 768
    if max(height, width) > max_side:
        rows = np.linspace(0, height - 1, max_side if height >= width
                           else max(8, int(round(height * max_side / width)))).astype(int)
        cols = np.linspace(0, width - 1, max_side if width >= height
                           else max(8, int(round(width * max_side / height)))).astype(int)
        image = image[np.ix_(rows, cols)]
    return image


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """取最可能的主体连通域，使用中心性避免选到贴边的背景色块。"""
    mask = np.asarray(mask, dtype=bool)
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    best: List[Tuple[float, List[Tuple[int, int]]]] = []
    center_y, center_x = (height - 1) / 2.0, (width - 1) / 2.0
    scale = max(height, width, 1) / 2.0
    for y, x in zip(*np.nonzero(mask)):
        if visited[y, x]:
            continue
        stack = [(int(y), int(x))]
        visited[y, x] = True
        pixels: List[Tuple[int, int]] = []
        while stack:
            cy, cx = stack.pop()
            pixels.append((cy, cx))
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if len(pixels) >= max(12, mask.size // 5000):
            mean_y = sum(item[0] for item in pixels) / len(pixels)
            mean_x = sum(item[1] for item in pixels) / len(pixels)
            distance = math.hypot(mean_y - center_y, mean_x - center_x) / scale
            centrality = max(0.05, 1.0 - min(1.0, distance))
            score = len(pixels) * (0.35 + 0.65 * centrality)
            item = (score, pixels)
            best.append(item)
    if not best:
        raise ValueError("没有识别到清晰的前景轮廓；请换一张主体与背景反差更大的图片。")
    # 不因为主体被图片底边裁切就丢掉它；面积与中心性已经足够排除角落里的小标志。
    pixels = max(best, key=lambda item: item[0])[1]
    result = np.zeros_like(mask, dtype=bool)
    ys, xs = zip(*pixels)
    result[np.asarray(ys), np.asarray(xs)] = True
    return result


def _otsu_threshold(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    low, high = float(np.min(values)), float(np.max(values))
    if high - low <= np.finfo(float).eps:
        return low
    scaled = np.clip((values - low) / (high - low) * 255.0, 0, 255).astype(np.uint8)
    histogram = np.bincount(scaled.reshape(-1), minlength=256).astype(float)
    weights = np.cumsum(histogram)
    means = np.cumsum(histogram * np.arange(256))
    total = means[-1]
    between = (total * weights - means) ** 2 / np.maximum(weights * (weights[-1] - weights), 1.0)
    threshold = float(np.argmax(between))
    return low + (high - low) * threshold / 255.0


def _trace_boundary(mask: np.ndarray) -> np.ndarray:
    """无 OpenCV 时用 Moore 邻域跟踪主体的外边界。"""
    ys, xs = np.nonzero(mask)
    if len(ys) < 3:
        raise ValueError("没有足够的前景像素生成轮廓。")
    start = (int(ys[np.argmin(ys * mask.shape[1] + xs)]),
             int(xs[np.argmin(ys * mask.shape[1] + xs)]))
    offsets = ((-1, 0), (-1, 1), (0, 1), (1, 1),
               (1, 0), (1, -1), (0, -1), (-1, -1))
    current = start
    backtrack = (start[0], start[1] - 1)
    initial_backtrack = backtrack
    contour = [current]
    limit = max(64, mask.size * 8)
    for _ in range(limit):
        rel = (backtrack[0] - current[0], backtrack[1] - current[1])
        try:
            direction = offsets.index(rel)
        except ValueError:
            direction = 6
        found = False
        for step in range(8):
            index = (direction + 1 + step) % 8
            dy, dx = offsets[index]
            ny, nx = current[0] + dy, current[1] + dx
            if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx]:
                before = offsets[(index - 1) % 8]
                backtrack = (current[0] + before[0], current[1] + before[1])
                current = (ny, nx)
                contour.append(current)
                found = True
                break
        if not found:
            break
        if len(contour) > 8 and current == start and backtrack == initial_backtrack:
            break
    points = np.asarray(contour, dtype=float)
    if len(points) < 3:
        raise ValueError("无法沿前景边界生成轮廓。")
    return points[:, 1] + 1j * (-points[:, 0])


def _resample_closed(points: Any, count: int) -> np.ndarray:
    values = np.asarray(points, dtype=np.complex128).reshape(-1)
    if values.size < 3:
        raise ValueError("图片外轮廓至少需要 3 个点。")
    keep = np.r_[True, np.abs(np.diff(values)) > np.finfo(float).eps]
    values = values[keep]
    if values.size < 3:
        raise ValueError("图片外轮廓过于简单，无法生成傅里叶轨迹。")
    closed = np.concatenate((values, values[:1]))
    lengths = np.abs(np.diff(closed))
    total = float(np.sum(lengths))
    if total <= np.finfo(float).eps:
        raise ValueError("图片外轮廓退化为一个点。")
    cumulative = np.r_[0.0, np.cumsum(lengths)]
    targets = np.linspace(0.0, total, count, endpoint=False)
    real = np.interp(targets, cumulative, closed.real)
    imag = np.interp(targets, cumulative, closed.imag)
    return real + 1j * imag


def extract_image_contour(source: Any, samples: int = DEFAULT_SAMPLES) -> np.ndarray:
    """从图片中提取最可能的主体外轮廓，并按弧长均匀采样。

    OpenCV 可用时优先使用 GrabCut + ``findContours``；否则使用 Pillow/NumPy 的
    自适应颜色阈值和连通域跟踪。返回值与 :func:`sample_shape` 一样，是居中的单位尺度复数数组。
    """
    image = _read_image(source)
    count = _clamp_int(samples, MIN_SAMPLES, MAX_SAMPLES, DEFAULT_SAMPLES)
    height, width = image.shape[:2]
    contour: Optional[np.ndarray] = None
    try:
        import cv2  # type: ignore
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        mask = np.zeros((height, width), np.uint8)
        margin = max(1, min(height, width) // 20)
        rect = (margin, margin, max(2, width - 2 * margin), max(2, height - 2 * margin))
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, rect, bgd_model, fgd_model, 4, cv2.GC_INIT_WITH_RECT)
        foreground = _largest_component((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD))
        # 填掉主体上的细窄凹口（例如细线/褶皱），保留整体外轮廓。
        foreground = cv2.morphologyEx(foreground.astype(np.uint8), cv2.MORPH_CLOSE,
                                      np.ones((9, 9), np.uint8)).astype(bool)
        ys, xs = np.nonzero(foreground)
        area = len(xs)
        touches = sum((xs.min() == 0, xs.max() == width - 1,
                       ys.min() == 0, ys.max() == height - 1)) if area else 4
        # GrabCut 在整面浅色墙 / 地面上有时会把背景连成一个大块；
        # 这种结果通常同时碰到两个边，或占据过大的横向范围，交给明暗阈值回退。
        reliable = bool(area >= max(24, height * width // 5000)
                        and touches < 2
                        and area < height * width * 0.45
                        and (xs.max() - xs.min()) < width * 0.55)
        if reliable:
            contours, _hierarchy = cv2.findContours(foreground.astype(np.uint8),
                                                     cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if contours:
                contour = contours[int(np.argmax([cv2.contourArea(item) for item in contours]))]
                contour = contour.reshape(-1, 2)[:, 0] + 1j * (-contour.reshape(-1, 2)[:, 1])
    except Exception:
        contour = None
    if contour is None:
        gray = image.astype(float) @ np.asarray([0.299, 0.587, 0.114])
        border = np.concatenate((gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]))
        border_level = float(np.median(border))
        # 常见的场景是深色主体站在浅色背景；用边框亮度估计背景，
        # 比对整张图做 Otsu 更不容易把白墙当成前景。深色背景则对称取亮部。
        if border_level >= 128.0:
            threshold = border_level - max(28.0, min(72.0, 0.16 * border_level))
            foreground = gray <= threshold
        else:
            threshold = border_level + max(28.0, min(72.0, 0.16 * (255.0 - border_level)))
            foreground = gray >= threshold
        ratio = float(np.mean(foreground))
        if ratio < 0.002 or ratio > 0.75:
            distance = np.sqrt(np.sum((image.astype(float)
                                       - np.median(image.reshape(-1, 3), axis=0)) ** 2, axis=2))
            score = distance + 0.75 * np.maximum(0.0, border_level - gray)
            fallback_threshold = float(np.percentile(score, 92.0))
            foreground = score >= fallback_threshold
        foreground = _largest_component(foreground)
        try:
            import cv2  # type: ignore
            foreground = cv2.morphologyEx(foreground.astype(np.uint8), cv2.MORPH_CLOSE,
                                          np.ones((9, 9), np.uint8)).astype(bool)
        except Exception:
            pass
        # OpenCV 可用时即使 GrabCut 被判为不可靠，仍用它稳定地把阈值掩膜
        # 变成有序外轮廓；纯 NumPy 环境才使用简化的 Moore 跟踪回退。
        try:
            import cv2  # type: ignore
            contours, _hierarchy = cv2.findContours(foreground.astype(np.uint8),
                                                     cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            if contours:
                item = max(contours, key=cv2.contourArea).reshape(-1, 2)
                contour = item[:, 0] + 1j * (-item[:, 1])
        except Exception:
            pass
        if contour is None:
            contour = _trace_boundary(foreground)
    return _normalize_points(_resample_closed(contour, count))


def sample_shape(shape: str = DEFAULT_SHAPE, samples: int = DEFAULT_SAMPLES,
                 image_path: str = "") -> np.ndarray:
    """生成一个不重复首尾点的闭合轮廓，返回复数数组。"""
    key = str(shape).strip().lower()
    if key not in SHAPE_LABELS:
        raise ValueError(f"不支持的曲线：{shape!r}（可选：{', '.join(SHAPE_LABELS)}）")
    count = _clamp_int(samples, MIN_SAMPLES, MAX_SAMPLES, DEFAULT_SAMPLES)
    if key == "image":
        if not str(image_path).strip():
            raise ValueError("选择“图片轮廓”时，请先选择或输入图片路径。")
        return extract_image_contour(image_path, count)
    if key == "sample_image":
        try:
            points = np.asarray(json.loads(_SAMPLE_CONTOUR_FILE.read_text(encoding="utf-8")),
                                dtype=np.float64)
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"内置示例轮廓文件不可读：{_SAMPLE_CONTOUR_FILE}") from exc
        return _normalize_points(_resample_closed(points[:, 0] + 1j * points[:, 1], count))
    theta = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    if key == "circle":
        values = np.exp(1j * theta)
    elif key == "heart":
        x = 16.0 * np.sin(theta) ** 3
        y = (13.0 * np.cos(theta) - 5.0 * np.cos(2 * theta)
             - 2.0 * np.cos(3 * theta) - np.cos(4 * theta))
        values = x + 1j * y
    elif key == "star":
        radius = np.where((theta / (2 * np.pi) * 10).astype(int) % 2 == 0, 1.0, 0.43)
        values = radius * np.exp(1j * (theta - np.pi / 2.0))
    elif key == "flower":
        radius = 0.72 + 0.28 * np.cos(5.0 * theta)
        values = radius * np.exp(1j * theta)
    else:  # lissajous
        values = np.sin(3.0 * theta + np.pi / 2.0) + 1j * np.sin(2.0 * theta)
    return _normalize_points(values)


def dft_coefficients(points: Any, terms: int = DEFAULT_TERMS) -> Tuple[np.ndarray, np.ndarray]:
    """返回按旋转顺序排列的 ``(频率, 复系数)``。

    排序为 ``0, +1, -1, +2, -2, ...``，这样低频圆会先画，动画更容易读。
    """
    values = _normalize_points(points)
    count = values.size
    spectrum = np.fft.fft(values) / count
    frequencies = np.rint(np.fft.fftfreq(count) * count).astype(int)
    order = sorted(range(count), key=lambda i: (abs(int(frequencies[i])),
                                                 0 if frequencies[i] >= 0 else 1))
    take = _clamp_int(terms, MIN_TERMS, min(MAX_TERMS, count), DEFAULT_TERMS)
    selected = order[:take]
    return frequencies[selected], spectrum[selected]


def evaluate_series(frequencies: Sequence[int], coefficients: Sequence[complex],
                    times: Any) -> np.ndarray:
    """在归一化时间 ``times ∈ [0, 1]`` 上求旋转矢量末端。"""
    freq = np.asarray(frequencies, dtype=float).reshape(-1)
    coeff = np.asarray(coefficients, dtype=np.complex128).reshape(-1)
    if freq.size != coeff.size or not freq.size:
        raise ValueError("频率和系数必须是同样的非空长度。")
    time_values = np.asarray(times, dtype=float)
    return np.sum(coeff[:, None] * np.exp(2j * np.pi * freq[:, None] * time_values.reshape(1, -1)), axis=0)


def _chain(frequencies: Sequence[int], coefficients: Sequence[complex], time_value: float) -> np.ndarray:
    vectors = np.asarray(coefficients, dtype=np.complex128) * np.exp(
        2j * np.pi * np.asarray(frequencies, dtype=float) * float(time_value))
    return np.concatenate(([0.0 + 0.0j], np.cumsum(vectors)))


@dataclass(frozen=True)
class FourierResult:
    shape: str
    samples: int
    terms: int
    frames: int
    frequencies: np.ndarray
    coefficients: np.ndarray
    source: np.ndarray
    approximation: np.ndarray
    trajectory: np.ndarray
    rmse: float
    elapsed: float

    def harmonics(self) -> List[Dict[str, float]]:
        return [
            {
                "frequency": int(frequency),
                "real": float(coefficient.real),
                "imag": float(coefficient.imag),
                "amplitude": float(abs(coefficient)),
                "phase": float(np.angle(coefficient)),
            }
            for frequency, coefficient in zip(self.frequencies, self.coefficients)
        ]

    def records(self) -> List[Dict[str, float]]:
        return [
            {"step": index + 1, "x": float(value.real), "y": float(value.imag)}
            for index, value in enumerate(self.trajectory)
        ]


def analyze_points(points: Any, terms: int = DEFAULT_TERMS,
                   frames: int = DEFAULT_FRAMES, shape: str = "custom") -> FourierResult:
    """分析任意有序轮廓点，并返回可供动画视图使用的结果。"""
    started = time.perf_counter()
    source = _normalize_points(points)
    frequencies, coefficients = dft_coefficients(source, terms)
    approximation = evaluate_series(frequencies, coefficients,
                                    np.arange(source.size, dtype=float) / source.size)
    trajectory = evaluate_series(frequencies, coefficients,
                                 np.arange(_clamp_int(frames, MIN_FRAMES, MAX_FRAMES,
                                                       DEFAULT_FRAMES), dtype=float)
                                 / _clamp_int(frames, MIN_FRAMES, MAX_FRAMES, DEFAULT_FRAMES))
    rmse = float(np.sqrt(np.mean(np.abs(approximation - source) ** 2)))
    return FourierResult(str(shape), int(source.size), int(len(frequencies)),
                         int(trajectory.size), frequencies, coefficients, source,
                         approximation, trajectory, rmse,
                         time.perf_counter() - started)


class FourierEpicycle:
    """内置轮廓的对象级 API。"""

    def __init__(self, shape: str = DEFAULT_SHAPE, samples: int = DEFAULT_SAMPLES,
                 terms: int = DEFAULT_TERMS, frames: int = DEFAULT_FRAMES,
                 image_path: str = "") -> None:
        key = str(shape).strip().lower()
        if key not in SHAPE_LABELS:
            key = DEFAULT_SHAPE
        self.shape = key
        self.samples = _clamp_int(samples, MIN_SAMPLES, MAX_SAMPLES, DEFAULT_SAMPLES)
        self.terms = _clamp_int(terms, MIN_TERMS, min(MAX_TERMS, self.samples), DEFAULT_TERMS)
        self.frames = _clamp_int(frames, MIN_FRAMES, MAX_FRAMES, DEFAULT_FRAMES)
        self.image_path = str(image_path or "").strip()

    def analyze(self) -> FourierResult:
        return analyze_points(sample_shape(self.shape, self.samples, self.image_path), self.terms,
                              self.frames, self.shape)


def _selfcheck() -> None:
    result = FourierEpicycle().analyze()
    circle = sample_shape("circle", 256)
    frequencies, coefficients = dft_coefficients(circle, 5)
    print("Fourier Epicycles 自检")
    print(f"默认曲线 {SHAPE_LABELS[result.shape]}：{result.samples} 个采样点，"
          f"保留 {result.terms} 个旋转向量，{result.frames} 帧")
    print(f"首个频率序列：{','.join(str(int(v)) for v in frequencies)}")
    print(f"圆形主频：k={int(frequencies[np.argmax(np.abs(coefficients))])}，"
          f"幅度 {float(np.max(np.abs(coefficients))):.6f}")
    print(f"截断均方根误差 {result.rmse:.6f}")


if __name__ == "__main__":  # pragma: no cover
    _selfcheck()
