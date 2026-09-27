# -*- coding: utf-8 -*-
"""抛体运动实验室。"""

from ...registry import register
from .model import ProjectileMotion, ProjectileResult
from .spec import build_spec

SPEC = register(build_spec())

__all__ = ["SPEC", "ProjectileMotion", "ProjectileResult"]
