from __future__ import annotations

import numpy as np


def compute_slope(elevation: np.ndarray, resolution_m: float) -> np.ndarray:
    """
    Compute terrain slope in degrees using NumPy gradient.
    """
    dy, dx = np.gradient(elevation, resolution_m, resolution_m)
    # Slope in radians
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    # Convert to degrees
    slope_deg = np.degrees(slope_rad)
    return slope_deg.astype(np.float32)


def compute_d8_flow_direction(elevation: np.ndarray) -> np.ndarray:
    """
    Compute D8 flow direction (ESRI encoding).
    East=1, SE=2, S=4, SW=8, W=16, NW=32, N=64, NE=128
    """
    # ESRI D8 direction mapping
    # Note: Row indices increase downwards (North to South)
    # Col indices increase rightwards (West to East)
    # (dy, dx): (direction_value, distance_weight)
    neighbors = [
        (0, 1, 1, 1.0),        # East
        (1, 1, 2, 1.41421),    # South-East
        (1, 0, 4, 1.0),        # South
        (1, -1, 8, 1.41421),   # South-West
        (0, -1, 16, 1.0),      # West
        (-1, -1, 32, 1.41421), # North-West
        (-1, 0, 64, 1.0),      # North
        (-1, 1, 128, 1.41421), # North-East
    ]

    h, w = elevation.shape
    max_drop = np.zeros_like(elevation, dtype=np.float32)
    flow_dir = np.zeros_like(elevation, dtype=np.uint8)

    # Calculate steepest descent
    for dy, dx, direction, dist in neighbors:
        # Create shifted arrays
        y_start, y_end = max(0, -dy), min(h, h - dy)
        x_start, x_end = max(0, -dx), min(w, w - dx)
        
        y_n_start, y_n_end = max(0, dy), min(h, h + dy)
        x_n_start, x_n_end = max(0, dx), min(w, w + dx)

        elev_center = elevation[y_start:y_end, x_start:x_end]
        elev_neighbor = elevation[y_n_start:y_n_end, x_n_start:x_n_end]

        # Drop is positive if neighbor is lower
        drop = (elev_center - elev_neighbor) / dist

        # Find where this neighbor provides a steeper drop than previously found
        mask = drop > max_drop[y_start:y_end, x_start:x_end]

        # Update max_drop and flow_dir for those cells
        max_drop[y_start:y_end, x_start:x_end][mask] = drop[mask]
        flow_dir[y_start:y_end, x_start:x_end][mask] = direction

    return flow_dir


def compute_flow_accumulation(flow_direction: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """
    Compute flow accumulation using D8 routing by sorting cells by elevation.
    """
    h, w = elevation.shape
    accumulation = np.ones((h, w), dtype=np.float32)

    # Sort indices by elevation descending
    # Flatten elevation array to sort
    flat_elev = elevation.flatten()
    sorted_indices = np.argsort(flat_elev)[::-1]

    # Map directions to offset arrays (dy, dx)
    # 1:E, 2:SE, 4:S, 8:SW, 16:W, 32:NW, 64:N, 128:NE
    dir_map = {
        1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1),
        16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)
    }

    # Iterate from highest to lowest elevation
    for idx in sorted_indices:
        y, x = divmod(idx, w)
        direction = flow_direction[y, x]
        if direction in dir_map:
            dy, dx = dir_map[direction]
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                accumulation[ny, nx] += accumulation[y, x]

    return accumulation


def compute_low_lying_index(elevation: np.ndarray, flow_accumulation: np.ndarray) -> np.ndarray:
    """
    Compute a composite low-lying index based on elevation percentiles and flow accumulation.
    Values closer to 1.0 represent high-risk low-lying areas.
    """
    valid_elev = np.ma.masked_invalid(elevation)
    valid_acc = np.ma.masked_invalid(flow_accumulation)
    
    # Avoid division by zero
    min_e, max_e = valid_elev.min(), valid_elev.max()
    elev_range = max_e - min_e if max_e > min_e else 1.0
    
    # Invert elevation: 1 = lowest point, 0 = highest point
    inv_elev_norm = (max_e - valid_elev) / elev_range
    
    # Normalize flow accumulation (log scale to handle extreme differences)
    log_acc = np.log1p(valid_acc)
    min_a, max_a = log_acc.min(), log_acc.max()
    acc_range = max_a - min_a if max_a > min_a else 1.0
    acc_norm = (log_acc - min_a) / acc_range

    # Composite index (geometric mean-like or simple product)
    low_lying = np.sqrt(inv_elev_norm * acc_norm)
    return low_lying.filled(np.nan).astype(np.float32)
