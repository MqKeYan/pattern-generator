// Periodic five-model update. Inputs and outputs are distinct float32 buffers.
__kernel void step(const int model,
                   __global const float *x, __global const float *y,
                   __global const float *p,
                   __global float *out_x, __global float *out_y,
                   const int height, const int width) {
    const int row = get_global_id(0);
    const int col = get_global_id(1);
    if (row >= height || col >= width) return;
    const int up = row == 0 ? height - 1 : row - 1;
    const int down = row + 1 == height ? 0 : row + 1;
    const int left = col == 0 ? width - 1 : col - 1;
    const int right = col + 1 == width ? 0 : col + 1;
    const int pos = row * width + col;
    const float xv = x[pos];
    const float yv = y[pos];
    const float lx = x[up*width+col] + x[down*width+col]
                   + x[row*width+left] + x[row*width+right] - 4.0f*xv;
    const float ly = y[up*width+col] + y[down*width+col]
                   + y[row*width+left] + y[row*width+right] - 4.0f*yv;
    float nx = 0.0f, ny = 0.0f;
    if (model == 0) {
        const float rx = p[0]*(1.0f-xv/p[2]) - yv/(p[1]+xv*xv);
        const float ry = p[4]*xv/(p[1]+xv*xv) - p[3];
        nx = xv*exp(rx) + p[5]*lx;
        ny = yv*exp(ry) + p[6]*ly;
    } else if (model == 1) {
        const float functional = p[1]*xv*yv/(xv*xv+p[2]);
        nx = p[0]*xv*(1.0f-xv/p[7]) - functional + p[5]*lx;
        ny = p[3]*functional - p[4]*yv + p[6]*ly;
    } else if (model == 2) {
        const float rx = p[0]*yv/(p[1]+xv) - p[0]/p[5]*xv;
        const float ry = p[3]*xv/(p[4]+xv);
        nx = xv*exp(rx) + p[6]*lx;
        ny = 1.0f-p[2]+p[2]*yv-ry+p[7]*ly;
    } else if (model == 3) {
        nx = p[0]*xv/(1.0f+xv+p[1]*yv) + p[2]*lx;
        ny = p[0]*yv/(1.0f+p[1]*xv+yv) + p[2]*ly;
    } else {
        const float functional = p[0]*p[3]*xv*yv/(p[1]+xv);
        nx = (1.0f+p[3]*p[5])*xv - p[3]*p[5]/p[4]*xv*xv - functional + p[6]*lx;
        ny = (1.0f-p[3]*p[2])*yv - functional + p[7]*ly;
    }
    out_x[pos] = fmax(nx, 1.0e-6f);
    out_y[pos] = fmax(ny, 1.0e-6f);
}
