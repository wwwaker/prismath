"""可选计算后端：数值一致、按需导入，以及无 Numba 时的行为。"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

from prismath.models.mandelbrot import (
    Mandelbrot, NUMBA_AUTO_MIN_POINTS, Viewport, complex_grid, escape_counts,
    mandelbrot_levels, numba_available, resolve_backend, scan_iterations,
)
from prismath.models.mandelbrot.spec import build_mandelbrot, options_from_ui


class BackendSelectionTest(unittest.TestCase):
    def test_default_and_view_changes(self):
        self.assertEqual(Mandelbrot().backend, "numpy")
        for name in ("numpy", "numba", "auto"):
            model = Mandelbrot(backend=name)
            self.assertEqual(model.zoomed(2).backend, name)
            self.assertEqual(model.with_view(Viewport(-1, 0.1, 0.5)).backend, name)

    def test_invalid_backend_rejected_even_for_empty_inputs(self):
        with self.assertRaises(ValueError):
            Mandelbrot(backend="typo")
        for points in (np.empty((0, 2)), [1j]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                escape_counts(points, backend="typo")

    def test_auto_resolves_at_compute_time(self):
        with patch("prismath.models.mandelbrot.model.numba_available", return_value=True):
            self.assertEqual(resolve_backend("auto", size=NUMBA_AUTO_MIN_POINTS - 1), "numpy")
            self.assertEqual(resolve_backend("auto", size=NUMBA_AUTO_MIN_POINTS), "numba")
        with patch("prismath.models.mandelbrot.model.numba_available", return_value=False):
            points = np.full((1, NUMBA_AUTO_MIN_POINTS), 3 + 0j)
            actual = escape_counts(points, backend="auto")
            expected = escape_counts(points)
            for a, b in zip(actual, expected):
                np.testing.assert_array_equal(a, b)

    def test_factory_environment_and_explicit_override(self):
        key = "PRISMATH_MANDELBROT_BACKEND"
        with patch.dict(os.environ, {key: ""}):
            self.assertEqual(build_mandelbrot({}).backend, "numpy")
        with patch.dict(os.environ, {key: "numba"}):
            self.assertEqual(build_mandelbrot(options_from_ui({})).backend, "numba")
            self.assertEqual(build_mandelbrot({"backend": "numpy"}).backend, "numpy")
            self.assertEqual(build_mandelbrot(options_from_ui({"backend": "auto"})).backend,
                             "auto")
        with patch.dict(os.environ, {key: "typo"}), self.assertRaises(ValueError):
            build_mandelbrot({})

    def test_missing_dependency_and_lazy_import_in_fresh_process(self):
        # A real import blocker also catches accidental eager imports. It works
        # whether or not the parent interpreter already loaded Numba.
        code = '''
import importlib.abc
import sys
class NoNumba(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numba' or fullname.startswith('numba.'):
            raise ModuleNotFoundError('Numba intentionally unavailable')
sys.meta_path.insert(0, NoNumba())
from prismath.models.mandelbrot import Mandelbrot, numba_available
assert 'numba' not in sys.modules
assert 'prismath.models.mandelbrot.numba_backend' not in sys.modules
assert not numba_available()
reference = Mandelbrot(pixels=520).render()
automatic = Mandelbrot(pixels=520, backend='auto').render()
assert (reference.counts == automatic.counts).all()
try:
    Mandelbrot(backend='numba').render()
except ImportError as exc:
    assert 'pip install numba' in str(exc)
else:
    raise AssertionError('Explicit Numba must report its missing dependency')
assert (Mandelbrot(pixels=520).render().counts == reference.counts).all()
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(numba_available(), "未安装可选依赖 Numba")
class NumbaNumericsTest(unittest.TestCase):
    def test_analytic_mask_matches_numpy(self):
        from prismath.models.mandelbrot.model import (
            INTERIOR_DISKS, _numba_interior_mask, interior_mask,
        )
        angles = np.linspace(0, 2 * np.pi, 1001)
        for cx, cy, radius in INTERIOR_DISKS:
            boundary = cx + 1j * cy + radius * np.exp(1j * angles)
            np.testing.assert_array_equal(_numba_interior_mask(boundary), interior_mask(boundary))
        points = complex_grid(Viewport(), 540, 720)
        np.testing.assert_array_equal(_numba_interior_mask(points), interior_mask(points))

    def assert_backends_equal(self, points, **kwargs):
        reference = escape_counts(points, backend="numpy", **kwargs)
        actual = escape_counts(points, backend="numba", **kwargs)
        np.testing.assert_array_equal(actual[0], reference[0])
        # math.log and np.log can differ by a few ULPs across platforms.
        np.testing.assert_allclose(actual[1], reference[1], rtol=2e-13, atol=2e-13)
        for a, b in zip(actual, reference):
            self.assertEqual(a.shape, b.shape)
            self.assertEqual(a.dtype, b.dtype)
        limit = max(1, int(kwargs.get("max_iter", 200)))
        np.testing.assert_array_equal(
            mandelbrot_levels(np.atleast_1d(actual[1]), limit, np.atleast_1d(actual[0]) > 0),
            mandelbrot_levels(np.atleast_1d(reference[1]), limit,
                              np.atleast_1d(reference[0]) > 0),
        )

    def test_known_points_and_bailout(self):
        points = np.array([0, -1, -2, 1, 2, 3, 1j, 2j, 0.5 + 0.5j, -0.75 + 0.1j])
        for skip in (True, False):
            for radius in (0, 2, 4, 10):
                with self.subTest(skip=skip, radius=radius):
                    self.assert_backends_equal(points, bailout=radius, skip_interior=skip)
        self.assert_backends_equal(points, max_iter=0)

    def test_shapes_and_noncontiguous_arrays(self):
        grid = complex_grid(Viewport(), 15, 20)
        for points in (3 + 0j, np.empty((2, 0)), grid, grid.T, grid[::-2, ::3],
                       np.array([0, -1]), grid.reshape(3, 5, 20)):
            with self.subTest(shape=np.shape(points)):
                self.assert_backends_equal(points)

    def test_fields_on_axis_off_axis_and_deep_zoom(self):
        cases = [
            dict(pixels=120, aspect=0.75, max_iter=200),
            dict(pixels=120, aspect=91 / 120, max_iter=2000),
            dict(center_x=-0.743643887, center_y=0.131825904, span=0.05, max_iter=400),
            dict(center_x=-0.743643887, center_y=0.131825904, span=0.0002, max_iter=1000),
            dict(center_x=-0.743643887, center_y=0.131825904, span=0.000001, max_iter=4000,
                 pixels=120),
        ]
        for kwargs in cases:
            with self.subTest(**kwargs):
                reference = Mandelbrot(**kwargs).render()
                actual = Mandelbrot(**kwargs, backend="numba").render()
                np.testing.assert_array_equal(actual.counts, reference.counts)
                np.testing.assert_allclose(actual.smooth, reference.smooth,
                                           rtol=2e-13, atol=2e-13)
                np.testing.assert_array_equal(actual.level_array(), reference.level_array())
                self.assertEqual(actual.as_dict(), reference.as_dict())

    def test_no_analytic_shortcut(self):
        self.assert_backends_equal(complex_grid(Viewport(), 60, 80), max_iter=500,
                                   skip_interior=False)

    def test_iteration_scan(self):
        expected = scan_iterations([10, 100, 300], pixels=80)
        actual = scan_iterations([10, 100, 300], pixels=80, backend="numba")
        for (limit, a), (reference_limit, b) in zip(actual, expected):
            self.assertEqual(limit, reference_limit)
            np.testing.assert_array_equal(a.counts, b.counts)
            np.testing.assert_array_equal(a.levels, b.levels)

    @unittest.skipUnless(importlib.util.find_spec("tkinter"), "未安装 tkinter")
    def test_tk_payload_from_background_thread(self):
        # 独立进程也验证首次加载发生在工作线程。避免前面的 Tk 交互测试残留的
        # 窗口引用被此测试的工作线程 GC 回收（Tcl 必须在创建窗口的线程销毁）。
        code = '''
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from prismath.models.mandelbrot import Viewport
from prismath.models.mandelbrot.views.tk import MandelbrotView
params = {'iterations': 400}
viewport = Viewport(-0.743643887, 0.131825904, 0.05)
expected = MandelbrotView._render_payload({**params, 'backend': 'numpy'}, viewport, (120, 90))
os.environ['PRISMATH_MANDELBROT_BACKEND'] = 'numba'
with ThreadPoolExecutor(max_workers=1) as executor:
    actual = executor.submit(MandelbrotView._render_payload, params,
                             viewport, (120, 90)).result(timeout=60)
np.testing.assert_array_equal(actual['values'], expected['values'])
assert actual['inside'] == expected['inside']
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, cwd=Path(__file__).resolve().parents[1], timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
