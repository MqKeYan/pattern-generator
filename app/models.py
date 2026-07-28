"""数学模型定义 - 5种捕食者-猎物斑图模型"""

import torch

def laplacian(Z):
    """二维拉普拉斯算子（周期性边界）"""
    return (
        torch.roll(Z, 1, 0) +
        torch.roll(Z, -1, 0) +
        torch.roll(Z, 1, 1) +
        torch.roll(Z, -1, 1) -
        4.0 * Z
    )

def model_1(x, y, p):
    """模型1：Rosenzweig-MacArthur 型捕食者-猎物模型
    参数：r, a, K, d, mu, D1, D2"""
    r, a, K, d, mu, D1, D2 = p

    rx = r * (1.0 - x / K) - y / (a + x * x)
    ry = (mu * x) / (a + x * x) - d

    x_next = x * torch.exp(rx) + D1 * laplacian(x)
    y_next = y * torch.exp(ry) + D2 * laplacian(y)

    return torch.clamp(x_next, min=1e-6), torch.clamp(y_next, min=1e-6)

def model_2(x, y, p):
    """模型2：Holling II 型捕食者-猎物模型
    参数：r, a, b, c1, c2, D1, D2, R"""
    r, a, b, c1, c2, D1, D2, R = p

    functional = a * x * y / (x**2 + b)

    x_next = r * x * (1 - x / R) - functional + D1 * laplacian(x)
    y_next = c1 * functional - c2 * y + D2 * laplacian(y)

    return torch.clamp(x_next, min=1e-6), torch.clamp(y_next, min=1e-6)

def model_3(x, y, p):
    """模型3：Ratio-dependent 捕食者-猎物模型
    参数：r, a, b, c, d, k, D1, D2"""
    r, a, b, c, d, k, D1, D2 = p

    rx = (r * y) / (a + x) - r / k * x
    ry = (c * x) / (d + x)

    x_next = x * torch.exp(rx) + D1 * laplacian(x)
    y_next = 1 - b + b * y - ry + D2 * laplacian(y)

    return torch.clamp(x_next, min=1e-6), torch.clamp(y_next, min=1e-6)

def model_4(x, y, p):
    """模型4：对称竞争模型
    参数：r, a, D"""
    r, a, D = p

    rx = x / (1 + x + a * y)
    ry = y / (1 + a * x + y)

    x_next = r * rx + D * laplacian(x)
    y_next = r * ry + D * laplacian(y)

    return torch.clamp(x_next, min=1e-6), torch.clamp(y_next, min=1e-6)

def model_5(x, y, p):
    """模型5：连续化的离散捕食者-猎物模型
    参数：a, b, d, h, K, r, D1, D2"""
    a, b, d, h, K, r, D1, D2 = p

    functional = (a * h * x * y) / (b + x)

    x_next = (1 + h * r) * x - ((h * r) / K) * (x ** 2) - functional + D1 * laplacian(x)
    y_next = (1 - h * d) * y - functional + D2 * laplacian(y)

    return torch.clamp(x_next, min=1e-6), torch.clamp(y_next, min=1e-6)

# 模型函数映射
MODEL_FUNCS = {
    "模型1": model_1,
    "模型2": model_2,
    "模型3": model_3,
    "模型4": model_4,
    "模型5": model_5
}