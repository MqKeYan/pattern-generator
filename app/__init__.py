"""
斑图生成器 (Pattern Generator)
"""
from .engine.config import MODEL_CONFIGS, GRID_SIZE, MODEL_INIT_RANGES, PARAM_MEANINGS
from .engine.models import MODEL_FUNCS, laplacian
from .engine.simulator import PatternSimulator

__version__ = "1.3.1"
