"""
斑图生成器 (Pattern Generator)
"""
from .config import MODEL_CONFIGS, GRID_SIZE, MODEL_INIT_RANGES, PARAM_MEANINGS
from .models import MODEL_FUNCS, laplacian
from .simulator import PatternSimulator

__version__ = "1.3.0"
