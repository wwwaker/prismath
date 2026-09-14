# -*- coding: utf-8 -*-
"""
后台任务 mixin：批量统计与曲线扫描
==================================

批量统计 / 曲线扫描都耗时较长（数千次模拟），因此一律放到**后台线程**执行：

* 计算线程只把消息丢进 ``self._queue``（``("progress", ...)`` 等），绝不碰 Tk 控件；
* 主线程由基类 :meth:`~awe_math.ui.tk.kit.base.ModelViewBase._poll_queue` 定时轮询队列；
* 「停止」按钮置位 ``self._cancel``（:class:`threading.Event`），后台线程在每轮迭代检查它；
* 视图被切换 / 关闭时（:meth:`JobsMixin.shutdown`）取消挂起的动画并交给基类统一收尾。

线程与队列这些**通用机制**由 :class:`~awe_math.ui.tk.kit.base.ModelViewBase` 提供
（``_submit`` / ``_poll_queue`` / ``_set_busy`` / ``stop_work`` / ``shutdown``），本 mixin 只负责
"批量统计 / 曲线扫描"这两件渗流特有的事：调用子类 :meth:`_model_functions` 给出的模型函数，
并把回传结果刷进结果面板。
"""

from __future__ import annotations

from typing import Any, Dict

from .common import parse_float, parse_int
from .protocols import ViewContract

__all__ = ["JobsMixin"]


class JobsMixin(ViewContract):
    """后台任务（批量统计 + 曲线扫描）。"""

    # ------------------------------------------------------------------
    # 批量统计与曲线扫描共用的模型选项
    # ------------------------------------------------------------------
    def _batch_options(self) -> Dict[str, Any]:
        """批量统计与曲线扫描共用的模型选项（不含 p / 形状 / 次数）。"""
        model = self.model
        return {
            "lattice": model.lattice,
            "direction": model.direction,
            "inject": model.inject,
            "criterion": model.criterion,
            "threshold": model.threshold,
        }

    # ==================================================================
    # 启动后台任务
    # ==================================================================
    def start_batch_statistics(self) -> None:
        """对当前 p 值做 N 次独立实验，统计当前判据下的成功频率。"""
        if self._busy:
            return
        # 先把界面上的形状 / 格子 / 方向 / 注水 / 判据 / 阈值全部同步进模型，
        # 保证「统计的就是屏幕上看到的这一套设置」——不能依赖下拉框回调是否已经跑过
        self._sync_model_params()
        batch_runner, _scan_runner = self._model_functions()
        rows, cols = self._current_shape()
        p = round(self.var_p.get(), 2)
        model = self.model
        trials = parse_int(self.var_trials.get(), 1000)
        seed = self._current_seed()
        options = self._batch_options()
        self._cancel.clear()
        self.progress.configure(maximum=trials, value=0)
        self._set_busy(
            True,
            f"正在统计：{model.lattice_name} {rows}×{cols}，"
            f"{self._result_summary()}，p={p:.2f}，"
            f"共 {trials} 次独立{self._terms.trial_word}"
            + (f"（种子 {seed}）" if seed is not None else "") + "…",
        )

        def job() -> None:
            try:
                res = batch_runner(
                    rows=rows, cols=cols, p=p, trials=trials, rng=seed, **options,
                    progress=lambda done, total, success: self._queue.put(("progress", (done, total))),
                    cancel=self._cancel,
                )
                self._queue.put(("batch_done", res))
            except Exception as exc:  # pragma: no cover - 后台线程里的异常统一回传
                self._queue.put(("error", f"批量统计失败：{exc}"))

        self._submit(job)

    def start_scan(self) -> None:
        """扫描 p ∈ [0, 1]，绘制当前判据下的成功概率与平均活动比例曲线。"""
        if self._busy:
            return
        # 同批量统计：先同步界面设置，曲线必须反映当前的形状 / 格子 / 方向 / 注水 / 判据
        self._sync_model_params()
        _batch_runner, scan_runner = self._model_functions()
        rows, cols = self._current_shape()
        trials = parse_int(self.var_scan_trials.get(), 200, low=10)
        step = parse_float(self.var_scan_step.get(), 0.05, low=0.01, high=0.5)
        p_values = [round(i * step, 2) for i in range(int(round(1.0 / step)) + 1)]
        p_values = [p for p in p_values if p <= 1.0]

        model = self.model
        seed = self._current_seed()
        options = self._batch_options()
        self._cancel.clear()
        self._scan_results = []
        self._scan_meta = (rows, trials)
        self._scan_cols = cols
        self._scan_lattice = model.lattice
        self._scan_direction = model.direction
        self._scan_inject = model.inject
        self._scan_criterion = model.criterion
        self._scan_threshold = model.threshold
        self._scan_pc = model.theoretical_pc
        self.progress.configure(maximum=len(p_values), value=0)
        self.notebook.select(self.tab_curve)
        self._set_busy(
            True,
            f"{self._terms.scan_verb}（共 {len(p_values)} 个点，每点 {trials} 次，"
            f"{self._result_summary()}"
            + (f"，种子 {seed}" if seed is not None else "") + "）…",
        )

        def job() -> None:
            try:
                scan_runner(
                    p_values, rows=rows, cols=cols, trials=trials, rng=seed, **options,
                    progress=lambda done, total, res: self._queue.put(("scan_point", (done, total, res))),
                    cancel=self._cancel,
                )
                self._queue.put(("scan_done", None))
            except Exception as exc:  # pragma: no cover - 后台线程里的异常统一回传
                self._queue.put(("error", f"{self._terms.scan_error}：{exc}"))

        self._submit(job)

    # ==================================================================
    # 消息处理（在基类的轮询里被调用）
    # ==================================================================
    def _handle_message(self, kind: str, payload: Any) -> None:
        if kind == "progress":
            done, total = payload
            self.progress.configure(maximum=total, value=done)
            self.var_status.set(f"正在统计：{done}/{total} 次{self._terms.trial_word}…")

        elif kind == "batch_done":
            self._on_batch_done(payload)

        elif kind == "scan_point":
            done, total, res = payload
            self._scan_results.append(res)
            self.progress.configure(maximum=total, value=done)
            self.var_status.set(
                f"{self._terms.scan_progress}：{done}/{total} 个 p 值已计算…")
            self._redraw_curve()

        elif kind == "scan_done":
            self._set_busy(False)
            self._redraw_curve()
            self.var_status.set(
                f"曲线绘制完成：共 {len(self._scan_results)} 个点，"
                f"每点 {self._scan_meta[1]} 次{self._terms.curve_trial_word}。"
            )

        else:                       # error 等通用消息交回基类
            super()._handle_message(kind, payload)

    def _on_batch_done(self, res) -> None:
        """批量统计完成：刷新指标 / 历史表，并按判据给出「这个概率意味着什么」。"""
        terms = self._terms
        self._set_busy(False)
        self.progress.configure(value=self.progress.cget("maximum"))
        self.vals["b_p"].set(f"{res.p:.2f}")
        self.vals["b_trials"].set(f"{res.trials}")
        self.vals["b_success"].set(f"{res.success}")
        self.vals["b_prob"].set(f"{res.probability:.4f}（{res.probability:.2%}）")
        self.vals["b_mean"].set(f"{res.mean_ratio:.1%}")
        self.vals["b_err"].set(f"±{res.stderr:.4f}")
        self.vals["b_time"].set(f"{res.elapsed:.2f} s")
        self._insert_history(res, "ok" if res.probability >= 0.5 else "no")
        self.notebook.select(self.tab_batch)
        self.var_status.set(
            f"统计完成：{self._result_summary()}，p={res.p:.2f} 时"
            f"「{res.criterion_name}」的成功概率 ≈ {res.probability:.4f}"
            f"（{res.success}/{res.trials}），{terms.mean_short} {res.mean_ratio:.1%}，"
            f"耗时 {res.elapsed:.2f} s。{self._batch_tail(res)}"
        )

    def _batch_tail(self, res) -> str:
        """批量统计结论的补充说明（文案由判据策略给出）。"""
        return self._criterion_strategy(res.criterion).batch_tail(
            res, self.model, self._terms)

    # ==================================================================
    # 生命周期
    # ==================================================================
    def shutdown(self) -> None:
        """视图被关闭（或切换到别的模型）时先停动画，再交给基类统一释放。"""
        self._cancel_animation()
        super().shutdown()
