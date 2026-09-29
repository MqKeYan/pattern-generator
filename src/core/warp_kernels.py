"""Independent Warp CPU/CUDA update kernel; no PyTorch or CuPy interop."""
import warp as wp


@wp.kernel
def step(model: int, x: wp.array(dtype=wp.float32, ndim=2),
         y: wp.array(dtype=wp.float32, ndim=2),
         p: wp.array(dtype=wp.float32, ndim=1),
         out_x: wp.array(dtype=wp.float32, ndim=2),
         out_y: wp.array(dtype=wp.float32, ndim=2),
         height: int, width: int):
    row, col = wp.tid()
    up = row - 1
    down = row + 1
    left = col - 1
    right = col + 1
    if up < 0:
        up = height - 1
    if down == height:
        down = 0
    if left < 0:
        left = width - 1
    if right == width:
        right = 0
    xv = x[row, col]
    yv = y[row, col]
    lx = x[up, col] + x[down, col] + x[row, left] + x[row, right] - 4.0 * xv
    ly = y[up, col] + y[down, col] + y[row, left] + y[row, right] - 4.0 * yv
    nx = 0.0
    ny = 0.0
    if model == 0:
        rx = p[0] * (1.0 - xv / p[2]) - yv / (p[1] + xv * xv)
        ry = p[4] * xv / (p[1] + xv * xv) - p[3]
        nx = xv * wp.exp(rx) + p[5] * lx
        ny = yv * wp.exp(ry) + p[6] * ly
    elif model == 1:
        functional = p[1] * xv * yv / (xv * xv + p[2])
        nx = p[0] * xv * (1.0 - xv / p[7]) - functional + p[5] * lx
        ny = p[3] * functional - p[4] * yv + p[6] * ly
    elif model == 2:
        rx = p[0] * yv / (p[1] + xv) - p[0] / p[5] * xv
        ry = p[3] * xv / (p[4] + xv)
        nx = xv * wp.exp(rx) + p[6] * lx
        ny = 1.0 - p[2] + p[2] * yv - ry + p[7] * ly
    elif model == 3:
        nx = p[0] * xv / (1.0 + xv + p[1] * yv) + p[2] * lx
        ny = p[0] * yv / (1.0 + p[1] * xv + yv) + p[2] * ly
    else:
        functional = p[0] * p[3] * xv * yv / (p[1] + xv)
        nx = (1.0 + p[3] * p[5]) * xv - p[3] * p[5] / p[4] * xv * xv - functional + p[6] * lx
        ny = (1.0 - p[3] * p[2]) * yv - functional + p[7] * ly
    if nx < 1e-6:
        nx = 1e-6
    if ny < 1e-6:
        ny = 1e-6
    out_x[row, col] = nx
    out_y[row, col] = ny
