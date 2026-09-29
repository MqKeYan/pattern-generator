"""CPU-only Numba kernels; loaded only by the external Numba worker."""
import math
import numba as nb


@nb.njit(inline='always')
def _cell(model, x, y, p, lx, ly):
    if model == 0:
        rx = p[0] * (1.0 - x / p[2]) - y / (p[1] + x * x)
        ry = p[4] * x / (p[1] + x * x) - p[3]
        nx = x * math.exp(rx) + p[5] * lx
        ny = y * math.exp(ry) + p[6] * ly
    elif model == 1:
        functional = p[1] * x * y / (x * x + p[2])
        nx = p[0] * x * (1.0 - x / p[7]) - functional + p[5] * lx
        ny = p[3] * functional - p[4] * y + p[6] * ly
    elif model == 2:
        rx = p[0] * y / (p[1] + x) - p[0] / p[5] * x
        ry = p[3] * x / (p[4] + x)
        nx = x * math.exp(rx) + p[6] * lx
        ny = 1.0 - p[2] + p[2] * y - ry + p[7] * ly
    elif model == 3:
        nx = p[0] * x / (1.0 + x + p[1] * y) + p[2] * lx
        ny = p[0] * y / (1.0 + p[1] * x + y) + p[2] * ly
    else:
        functional = p[0] * p[3] * x * y / (p[1] + x)
        nx = (1.0 + p[3] * p[5]) * x - p[3] * p[5] / p[4] * x * x - functional + p[6] * lx
        ny = (1.0 - p[3] * p[2]) * y - functional + p[7] * ly
    return max(nx, 1e-6), max(ny, 1e-6)


@nb.njit(cache=True)
def step_serial(model, x, y, p, out_x, out_y):
    height, width = x.shape
    for row in range(height):
        up = (row - 1) % height
        down = (row + 1) % height
        for col in range(width):
            left = (col - 1) % width
            right = (col + 1) % width
            xv, yv = x[row, col], y[row, col]
            lx = x[up, col] + x[down, col] + x[row, left] + x[row, right] - 4.0 * xv
            ly = y[up, col] + y[down, col] + y[row, left] + y[row, right] - 4.0 * yv
            out_x[row, col], out_y[row, col] = _cell(model, xv, yv, p, lx, ly)


@nb.njit(cache=True, parallel=True)
def step_parallel(model, x, y, p, out_x, out_y):
    height, width = x.shape
    for row in nb.prange(height):
        up = (row - 1) % height
        down = (row + 1) % height
        for col in range(width):
            left = (col - 1) % width
            right = (col + 1) % width
            xv, yv = x[row, col], y[row, col]
            lx = x[up, col] + x[down, col] + x[row, left] + x[row, right] - 4.0 * xv
            ly = y[up, col] + y[down, col] + y[row, left] + y[row, right] - 4.0 * yv
            out_x[row, col], out_y[row, col] = _cell(model, xv, yv, p, lx, ly)
