"""Taichi ndarray kernel shared by the explicit CPU/CUDA/Vulkan backends."""
import taichi as ti


@ti.kernel
def step(model: ti.i32,
         x: ti.types.ndarray(dtype=ti.f32, ndim=2),
         y: ti.types.ndarray(dtype=ti.f32, ndim=2),
         p: ti.types.ndarray(dtype=ti.f32, ndim=1),
         out_x: ti.types.ndarray(dtype=ti.f32, ndim=2),
         out_y: ti.types.ndarray(dtype=ti.f32, ndim=2),
         height: ti.i32, width: ti.i32):
    for row, col in ti.ndrange(height, width):
        up = (row + height - 1) % height
        down = (row + 1) % height
        left = (col + width - 1) % width
        right = (col + 1) % width
        xv = x[row, col]
        yv = y[row, col]
        lx = x[up, col] + x[down, col] + x[row, left] + x[row, right] - 4.0 * xv
        ly = y[up, col] + y[down, col] + y[row, left] + y[row, right] - 4.0 * yv
        nx = 0.0
        ny = 0.0
        if model == 0:
            rx = p[0] * (1.0 - xv / p[2]) - yv / (p[1] + xv * xv)
            ry = p[4] * xv / (p[1] + xv * xv) - p[3]
            nx = xv * ti.exp(rx) + p[5] * lx
            ny = yv * ti.exp(ry) + p[6] * ly
        elif model == 1:
            functional = p[1] * xv * yv / (xv * xv + p[2])
            nx = p[0] * xv * (1.0 - xv / p[7]) - functional + p[5] * lx
            ny = p[3] * functional - p[4] * yv + p[6] * ly
        elif model == 2:
            rx = p[0] * yv / (p[1] + xv) - p[0] / p[5] * xv
            ry = p[3] * xv / (p[4] + xv)
            nx = xv * ti.exp(rx) + p[6] * lx
            ny = 1.0 - p[2] + p[2] * yv - ry + p[7] * ly
        elif model == 3:
            nx = p[0] * xv / (1.0 + xv + p[1] * yv) + p[2] * lx
            ny = p[0] * yv / (1.0 + p[1] * xv + yv) + p[2] * ly
        else:
            functional = p[0] * p[3] * xv * yv / (p[1] + xv)
            nx = (1.0 + p[3] * p[5]) * xv - p[3] * p[5] / p[4] * xv * xv - functional + p[6] * lx
            ny = (1.0 - p[3] * p[2]) * yv - functional + p[7] * ly
        out_x[row, col] = ti.max(nx, 1e-6)
        out_y[row, col] = ti.max(ny, 1e-6)
