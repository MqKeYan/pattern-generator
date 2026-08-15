"""配置文件 - 模型配置和参数映射"""

# 模型配置字典
MODEL_CONFIGS = {
    "模型1": {
        "params": ["r", "a", "K", "d", "mu", "D1", "D2"],
        "defaults": [0.2, 0.5, 2.0, 0.3, 1.2, 0.05, 0.2],
        "min_iterations": 100,
        "max_iterations": 50000,
        "recommended_iterations": 9000,
        "description": "Rosenzweig-MacArthur 型捕食者-猎物模型"
    },
    "模型2": {
        "params": ["r", "a", "b", "c1", "c2", "D1", "D2", "R"],
        "defaults": [1.3, 0.9, 0.04, 1.173, 0.18, 0.002, 0.03, 0.5],
        "min_iterations": 100,
        "max_iterations": 50000,
        "recommended_iterations": 15000,
        "description": "Holling II 型捕食者-猎物模型"
    },
    "模型3": {
        "params": ["r", "a", "b", "c", "d", "k", "D1", "D2"],
        "defaults": [2.85, 0.28, 0.6, 0.815, 0.32, 3.88, 0.003, 0.03],
        "min_iterations": 100,
        "max_iterations": 50000,
        "recommended_iterations": 15000,
        "description": "Ratio-dependent 捕食者-猎物模型"
    },
    "模型4": {
        "params": ["r", "a", "D"],
        "defaults": [2.2, 1.1, 0.18],
        "min_iterations": 100,
        "max_iterations": 50000,
        "recommended_iterations": 10000,
        "description": "对称竞争模型"
    },
    "模型5": {
        "params": ["a", "b", "d", "h", "K", "r", "D1", "D2"],
        "defaults": [0.7, 0.55, 0.35, 0.001, 0.9, 0.75, 0.0008, 0.01],
        "min_iterations": 100,
        "max_iterations": 50000,
        "recommended_iterations": 4000,
        "description": "连续化的离散捕食者-猎物模型"
    }
}

# 各个模型的最佳初始值范围
MODEL_INIT_RANGES = {
    "模型1": {
        "x_range": (0.95, 1.05),
        "y_range": (0.80, 1.0),
        "description": "猎物密度较高，捕食者密度适中，适合形成螺旋波"
    },
    "模型2": {
        "x_range": (0.90, 1.00),
        "y_range": (0.40, 0.50),
        "description": "中等密度范围，适合形成条纹斑图"
    },
    "模型3": {
        "x_range": (0.49, 0.51),
        "y_range": (0.99, 1.01),
        "description": "较高密度范围，适合形成螺旋波和靶波"
    },
    "模型4": {
        "x_range": (0.45, 0.55),
        "y_range": (0.45, 0.55),
        "description": "两个物种密度相近，适合形成竞争斑图"
    },
    "模型5": {
        "x_range": (0.55, 0.60),
        "y_range": (0.25, 0.30),
        "description": "中等偏高密度，适合形成复杂动态斑图"
    }
}

# 参数中文名称映射
PARAM_NAMES = {
    "r": "增长率",
    "a": "响应系数",
    "b": "响应常数",
    "c": "捕食效率",
    "c1": "能量转换率",
    "c2": "捕食者死亡率",
    "d": "捕食者死亡率",
    "h": "时间步长系数",
    "k": "环境承载力",
    "K": "环境承载力",
    "mu": "转化效率",
    "R": "猎物承载量",
    "D": "扩散率",
    "D1": "猎物扩散率",
    "D2": "捕食者扩散率",
}

# 模型显示名称映射
MODEL_DISPLAY_NAMES = {
    "模型1": "模型1·R-M型",
    "模型2": "模型2·Holling II型",
    "模型3": "模型3·比值依赖型",
    "模型4": "模型4·对称竞争",
    "模型5": "模型5·连续化离散型",
}

# 网格大小
GRID_SIZE = 100