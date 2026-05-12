"""骨架字引擎 — 二值图 → 骨架化 → SkeletonGraph → Stroke 提取

无 Qt/PySide6 依赖。
支持可插拔 backend: skimage (主力) / zhang_suen (fallback) / auto (自动选择)。
全流程：binary → skeletonize → build_graph → extract strokes → order → debug。
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from core.types import PixelPoint, PathConfig, Stroke


# ---- SkeletonGraph 数据结构 ----


@dataclass
class SkeletonGraph:
    """骨架图拓扑结构"""
    skeleton: np.ndarray                     # 骨架二值图 (0/255)
    height: int = 0
    width: int = 0
    endpoints: list[PixelPoint] = field(default_factory=list)
    branchpoints: list[PixelPoint] = field(default_factory=list)
    components: list[np.ndarray] = field(default_factory=list)
    edges: list[list[PixelPoint]] = field(default_factory=list)
    pruned_spur_count: int = 0
    stats: dict = field(default_factory=dict)


# ---- Binary 输入归一化 ----


def _normalize_binary(binary: np.ndarray) -> np.ndarray:
    """统一输入格式：any → bool array (True=前景)。

    接受: bool, 0/1 int, 0/255 uint8
    """
    arr = np.asarray(binary)
    return arr > 0


def _to_output(skeleton_bool: np.ndarray) -> np.ndarray:
    """统一输出格式：bool → uint8 (0/255)。"""
    return (skeleton_bool.astype(np.uint8)) * 255


# ---- Zhang-Suen 骨架化（fallback backend）----

# 8 邻域偏移 (dx, dy)，左上起顺时针
_ZS_NEIGHBORS = [
    (0, -1), (1, -1), (1, 0), (1, 1),
    (0, 1), (-1, 1), (-1, 0), (-1, -1),
]


def _zhang_suen_thin(binary: np.ndarray, max_iterations: int = 200) -> tuple[np.ndarray, int, str]:
    """Zhang-Suen 骨架化算法。纯 numpy 实现。

    Args:
        binary: 二值图 (bool, 0/1, 0/255 均可接受)
        max_iterations: 最大迭代次数（每轮 = step1 + step2）

    Returns:
        (skeleton_uint8, iteration_count, warning)
        - skeleton_uint8: np.ndarray (dtype=uint8, 0=背景, 255=前景)
        - iteration_count: 实际消耗的轮数
        - warning: 空字符串或 warning 文本
    """
    img = _normalize_binary(binary).astype(np.uint8)
    skeleton = img.copy()
    iteration = 0
    warning = ""

    while iteration < max_iterations:
        changed = False

        to_remove = _zs_subiter(skeleton, step=1)
        if to_remove.any():
            skeleton[to_remove] = 0
            changed = True

        to_remove = _zs_subiter(skeleton, step=2)
        if to_remove.any():
            skeleton[to_remove] = 0
            changed = True

        iteration += 1
        if not changed:
            break

    if iteration >= max_iterations:
        warning = f"Zhang-Suen reached max_iterations={max_iterations} without converging"

    return _to_output(skeleton), iteration, warning


def _zs_subiter(img: np.ndarray, step: int) -> np.ndarray:
    """Zhang-Suen 单次子迭代。step=1 删除东南边界, step=2 删除西北边界。"""
    h, w = img.shape
    P = np.pad(img, 1, mode='constant')
    # 8 邻域 P2..P9, 从上方顺时针
    P2 = P[0:h,   1:w+1]   # 上
    P3 = P[0:h,   2:w+2]   # 右上
    P4 = P[1:h+1, 2:w+2]   # 右
    P5 = P[2:h+2, 2:w+2]   # 右下
    P6 = P[2:h+2, 1:w+1]   # 下
    P7 = P[2:h+2, 0:w]     # 左下
    P8 = P[1:h+1, 0:w]     # 左
    P9 = P[0:h,   0:w]     # 左上

    P1 = img
    ring = np.stack([P2, P3, P4, P5, P6, P7, P8, P9], axis=-1)
    ring_shifted = np.roll(ring, -1, axis=-1)
    A = np.sum((ring == 1) & (ring_shifted == 0), axis=-1)
    B = np.sum(ring, axis=-1)

    c1 = (B >= 2) & (B <= 6)
    c2 = (A == 1)

    if step == 1:
        c3 = (P2 * P4 * P6 == 0)
        c4 = (P4 * P6 * P8 == 0)
    else:
        c3 = (P2 * P4 * P8 == 0)
        c4 = (P2 * P6 * P8 == 0)

    return (P1 == 1) & c1 & c2 & c3 & c4


# ---- skimage 骨架化（主力 backend）----


def _skeletonize_skimage(binary: np.ndarray) -> tuple[np.ndarray, int, str]:
    """使用 skimage.morphology.skeletonize。

    Returns:
        (skeleton_uint8, iteration_count=0, warning)
    """
    try:
        from skimage.morphology import skeletonize as ski_skeletonize
    except ImportError as exc:
        raise ImportError(
            "skimage backend requested but skimage is not installed. "
            "Install with: pip install scikit-image"
        ) from exc

    img_bool = _normalize_binary(binary)
    result = ski_skeletonize(img_bool)
    return _to_output(result), 0, ""


# ---- Backend dispatcher ----


_SUPPORTED_BACKENDS = ("auto", "skimage", "zhang_suen")


def _skeletonize_backend(
    binary: np.ndarray,
    backend: str = "auto",
    max_iterations: int = 200,
) -> tuple[np.ndarray, str, int, str]:
    """骨架化后端分发。

    Args:
        binary: 二值图
        backend: "auto" | "skimage" | "zhang_suen"
        max_iterations: 仅对 zhang_suen 生效

    Returns:
        (skeleton_uint8, backend_used, iteration_count, warning)
    """
    if backend not in _SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unknown skeleton backend '{backend}'. "
            f"Supported: {', '.join(_SUPPORTED_BACKENDS)}"
        )

    if backend == "skimage":
        skel, iters, warn = _skeletonize_skimage(binary)
        return skel, "skimage", iters, warn

    if backend == "zhang_suen":
        skel, iters, warn = _zhang_suen_thin(binary, max_iterations=max_iterations)
        return skel, "zhang_suen", iters, warn

    # backend == "auto"
    try:
        skel, iters, warn = _skeletonize_skimage(binary)
        return skel, "skimage", iters, warn
    except ImportError:
        skel, iters, warn = _zhang_suen_thin(binary, max_iterations=max_iterations)
        return skel, "zhang_suen", iters, warn


# ---- SkeletonExtractor 类 ----


class SkeletonExtractor:
    """骨架字路径提取器。

    用法:
        ext = SkeletonExtractor()
        skeleton = ext.skeletonize_binary(binary, backend="auto")
        graph = ext.build_graph(skeleton)
    """

    # ---- skeletonize ----

    @staticmethod
    def skeletonize_binary(
        binary: np.ndarray,
        backend: str = "auto",
        smooth: bool = True,
        max_iterations: int = 200,
    ) -> tuple[np.ndarray, str, int, str]:
        """将二值图骨架化。

        Args:
            binary: 二值图 (bool / 0/1 / 0/255 均可接受)
            backend: "auto" | "skimage" | "zhang_suen"
            smooth: zhang_suen 前是否 Gaussian 平滑
            max_iterations: zhang_suen 最大迭代轮数

        Returns:
            (skeleton, backend_used, iteration_count, warning)
            - skeleton: np.ndarray (dtype=uint8, 0=背景, 255=前景)
            - backend_used: "skimage" | "zhang_suen"
            - iteration_count: zhang_suen 消耗轮数, skimage 为 0
            - warning: 空或警告文本
        """
        img = _normalize_binary(binary).astype(np.uint8) * 255

        if smooth and backend != "skimage":
            # Gaussian 平滑减少锯齿毛刺（skimage 内置处理更好，跳过）
            gray = img.astype(np.float32)
            blurred = cv2.GaussianBlur(gray, (5, 5), 1.0)
            img = (blurred > 127).astype(np.uint8) * 255

        return _skeletonize_backend(img, backend=backend, max_iterations=max_iterations)

    # ---- 端点/分叉点检测 ----

    @staticmethod
    def detect_endpoints(skeleton: np.ndarray) -> list[PixelPoint]:
        """检测骨架端点 (8 邻域中只有 1 个邻居)。"""
        skel = (skeleton > 0).astype(np.uint8)
        h, w = skel.shape
        padded = np.pad(skel, 1, mode='constant')
        endpoints = []
        for y in range(h):
            for x in range(w):
                if skel[y, x]:
                    n = int(np.sum(padded[y:y + 3, x:x + 3])) - 1
                    if n == 1:
                        endpoints.append(PixelPoint(x=float(x), y=float(y)))
        return endpoints

    @staticmethod
    def detect_branchpoints(skeleton: np.ndarray) -> list[PixelPoint]:
        """检测骨架分叉点 (8 邻域中 >= 3 个邻居)。"""
        skel = (skeleton > 0).astype(np.uint8)
        h, w = skel.shape
        padded = np.pad(skel, 1, mode='constant')
        branchpoints = []
        for y in range(h):
            for x in range(w):
                if skel[y, x]:
                    n = int(np.sum(padded[y:y + 3, x:x + 3])) - 1
                    if n >= 3:
                        branchpoints.append(PixelPoint(x=float(x), y=float(y)))
        return branchpoints

    # ---- 连通域分析 ----

    @staticmethod
    def connected_components(skeleton: np.ndarray) -> list[np.ndarray]:
        """基于骨架图的连通域分析。

        Returns:
            list[np.ndarray]: 每个连通域的 boolean mask
        """
        skel = (skeleton > 0).astype(np.uint8)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(skel, connectivity=8)
        components = []
        for i in range(1, stats.shape[0]):
            components.append((labels == i))
        return components

    # ---- 边追踪 ----

    @staticmethod
    def _trace_edges(skeleton: np.ndarray) -> list[list[PixelPoint]]:
        """从骨架图中追踪出所有边。"""
        skel = (skeleton > 0).astype(np.uint8)
        h, w = skel.shape
        special = set()
        for ep in SkeletonExtractor.detect_endpoints(skeleton):
            special.add((int(ep.x), int(ep.y)))
        for bp in SkeletonExtractor.detect_branchpoints(skeleton):
            special.add((int(bp.x), int(bp.y)))

        visited = np.zeros((h, w), dtype=bool)
        edges = []

        for sx, sy in list(special):
            if visited[sy, sx]:
                continue
            n_count = SkeletonExtractor._neighbor_count(skel, sx, sy)
            if n_count != 1:
                continue

            edge = SkeletonExtractor._trace_from(skel, visited, special, sx, sy)
            if len(edge) >= 2:
                edges.append([PixelPoint(x=float(px), y=float(py)) for px, py in edge])
                for px, py in edge:
                    if (px, py) not in special:
                        visited[py, px] = True

        # 孤立闭合环
        components = SkeletonExtractor.connected_components(skeleton)
        for comp in components:
            comp_ys, comp_xs = np.where(comp)
            all_visited = all(visited[y, x] for x, y in zip(comp_xs, comp_ys))
            if not all_visited and len(comp_xs) >= 3:
                for x, y in zip(comp_xs, comp_ys):
                    if not visited[y, x]:
                        loop = SkeletonExtractor._trace_loop(skel, visited, x, y)
                        if len(loop) >= 3:
                            edges.append([PixelPoint(x=float(px), y=float(py)) for px, py in loop])
                            for px, py in loop:
                                visited[py, px] = True
                        break
        return edges

    @staticmethod
    def _neighbor_count(skel: np.ndarray, x: int, y: int) -> int:
        h, w = skel.shape
        count = 0
        for dx, dy in _ZS_NEIGHBORS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
                count += 1
        return count

    @staticmethod
    def _trace_from(
        skel: np.ndarray, visited: np.ndarray, special: set,
        sx: int, sy: int,
    ) -> list[tuple[int, int]]:
        h, w = skel.shape
        edge = [(sx, sy)]
        cx, cy = sx, sy
        visited[cy, cx] = True
        while True:
            next_pts = []
            for dx, dy in _ZS_NEIGHBORS:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and skel[ny, nx] and not visited[ny, nx]:
                    next_pts.append((nx, ny))
            if len(next_pts) == 0:
                break
            nx, ny = next_pts[0]
            edge.append((nx, ny))
            visited[ny, nx] = True
            cx, cy = nx, ny
            if (cx, cy) in special:
                break
        return edge

    @staticmethod
    def _trace_loop(
        skel: np.ndarray, visited: np.ndarray,
        sx: int, sy: int,
    ) -> list[tuple[int, int]]:
        h, w = skel.shape
        loop = [(sx, sy)]
        cx, cy = sx, sy
        visited[cy, cx] = True
        while True:
            next_pts = []
            for dx, dy in _ZS_NEIGHBORS:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
                    if not visited[ny, nx]:
                        next_pts.append((nx, ny))
                    elif (nx, ny) == (sx, sy) and len(loop) >= 3:
                        return loop
            if len(next_pts) == 0:
                return loop
            nx, ny = next_pts[0]
            loop.append((nx, ny))
            visited[ny, nx] = True
            cx, cy = nx, ny
        return loop

    # ---- Spur pruning ----

    @staticmethod
    def spur_pruning(graph: 'SkeletonGraph', min_len_px: float = 3.0) -> 'SkeletonGraph':
        """删除短枝 (spur)。"""
        skel = (graph.skeleton > 0).astype(np.uint8)
        h, w = skel.shape
        eps = set((int(p.x), int(p.y)) for p in graph.endpoints)
        bps = set((int(p.x), int(p.y)) for p in graph.branchpoints)
        pruned_count = 0
        changed = True
        while changed:
            changed = False
            for ex, ey in list(eps):
                if not skel[ey, ex]:
                    continue
                cx, cy = ex, ey
                spur_pts = [(cx, cy)]
                while True:
                    next_pts = []
                    for dx, dy in _ZS_NEIGHBORS:
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
                            if (nx, ny) not in spur_pts:
                                next_pts.append((nx, ny))
                    if len(next_pts) == 1:
                        nx, ny = next_pts[0]
                        spur_pts.append((nx, ny))
                        cx, cy = nx, ny
                        if (cx, cy) in bps:
                            break
                    else:
                        break
                if len(spur_pts) < min_len_px:
                    for px, py in spur_pts:
                        if (px, py) not in bps:
                            skel[py, px] = 0
                    pruned_count += 1
                    eps.discard((ex, ey))
                    changed = True
                    break
        return SkeletonExtractor.build_graph(
            (skel * 255).astype(np.uint8), original_pruned=pruned_count,
        )

    # ---- build_graph ----

    @staticmethod
    def build_graph(
        skeleton: np.ndarray,
        original_pruned: int = 0,
        backend_used: str = "",
        iteration_count: int = 0,
        backend_warning: str = "",
    ) -> SkeletonGraph:
        """从骨架图构建 SkeletonGraph。

        Args:
            skeleton: 骨架二值图 (0/255)
            original_pruned: 之前 prune 的短枝数
            backend_used: 使用的 backend 名称
            iteration_count: zhang_suen 轮数
            backend_warning: backend 产生的 warning

        Returns:
            SkeletonGraph
        """
        skel = (skeleton > 0).astype(np.uint8)
        h, w = skel.shape

        endpoints = SkeletonExtractor.detect_endpoints(skeleton)
        branchpoints = SkeletonExtractor.detect_branchpoints(skeleton)
        components = SkeletonExtractor.connected_components(skeleton)
        edges = SkeletonExtractor._trace_edges(skeleton)

        stats = {
            "endpoint_count": len(endpoints),
            "branchpoint_count": len(branchpoints),
            "component_count": len(components),
            "edge_count": len(edges),
            "pruned_spur_count": original_pruned,
            "skeleton_pixel_count": int(np.sum(skel)),
            "skeleton_backend_used": backend_used,
            "skeleton_iteration_count": iteration_count,
            "skeleton_warning": backend_warning,
        }

        return SkeletonGraph(
            skeleton=skeleton,
            height=h,
            width=w,
            endpoints=endpoints,
            branchpoints=branchpoints,
            components=components,
            edges=edges,
            pruned_spur_count=original_pruned,
            stats=stats,
        )

    # ---- Stroke 提取 ----

    @staticmethod
    def extract(
        binary: np.ndarray,
        config: PathConfig | None = None,
        backend: str = "auto",
    ) -> tuple[list[Stroke], dict]:
        """主入口：binary → skeleton → graph → strokes + stats。

        Args:
            binary: 二值图 (bool / 0/1 / 0/255 均可接受)
            config: PathConfig, None 则用默认
            backend: "auto" | "skimage" | "zhang_suen"

        Returns:
            (strokes, stats)
            stats 透传 skeleton_backend_used / skeleton_iteration_count / skeleton_warning
        """
        cfg = config or PathConfig()

        skeleton, backend_used, iters, warn = SkeletonExtractor.skeletonize_binary(
            binary, backend=backend,
        )
        graph = SkeletonExtractor.build_graph(
            skeleton,
            backend_used=backend_used,
            iteration_count=iters,
            backend_warning=warn,
        )
        strokes = SkeletonExtractor._extract_strokes_from_graph(graph, cfg)
        strokes = SkeletonExtractor._order_strokes(strokes)
        strokes = SkeletonExtractor._merge_nearby_endpoints(strokes, threshold_px=0.0)

        stats = {
            "stroke_count": len(strokes),
            "closed_count": sum(1 for s in strokes if s.closed),
            "open_count": sum(1 for s in strokes if not s.closed),
            **graph.stats,
        }
        return strokes, stats

    @staticmethod
    def _extract_strokes_from_graph(
        graph: SkeletonGraph,
        config: PathConfig | None = None,
    ) -> list[Stroke]:
        """从 SkeletonGraph 提取 Stroke，合并 open 和 closed 两部分。"""
        strokes: list[Stroke] = []
        strokes.extend(SkeletonExtractor._extract_open_strokes(graph))
        strokes.extend(SkeletonExtractor._extract_closed_loops(graph))

        # 覆盖未追踪到的 component（孤立点块等）
        edge_pixel_set: set[tuple[int, int]] = set()
        for edge in graph.edges:
            for p in edge:
                edge_pixel_set.add((int(p.x), int(p.y)))
        ep_set: set[tuple[int, int]] = set(
            (int(ep.x), int(ep.y)) for ep in graph.endpoints
        )

        for comp in graph.components:
            comp_ys, comp_xs = np.where(comp)
            if len(comp_xs) == 0:
                continue
            comp_pixels = set(zip(comp_xs, comp_ys))
            if comp_pixels & edge_pixel_set:
                continue  # already covered

            eps_in_comp = sum(
                1 for ep in graph.endpoints
                if (int(ep.x), int(ep.y)) in comp_pixels
            )
            pts = [PixelPoint(x=float(x), y=float(y)) for x, y in zip(comp_xs, comp_ys)]
            pts.sort(key=lambda p: (p.y, p.x))
            strokes.append(Stroke(
                id=str(uuid.uuid4())[:8],
                source_type="skeleton",
                points_px=pts,
                closed=(eps_in_comp == 0 and len(pts) >= 3),
                is_hole=False,
            ))

        return strokes

    @staticmethod
    def _extract_open_strokes(graph: SkeletonGraph) -> list[Stroke]:
        """从 graph.edges 提取开放 Stroke。

        规则：edge 首或尾命中 endpoint → 开放路径。
        """
        strokes: list[Stroke] = []
        ep_set: set[tuple[int, int]] = set(
            (int(ep.x), int(ep.y)) for ep in graph.endpoints
        )

        for edge in graph.edges:
            if len(edge) < 2:
                continue
            first = (int(edge[0].x), int(edge[0].y))
            last = (int(edge[-1].x), int(edge[-1].y))
            if first in ep_set or last in ep_set:
                strokes.append(Stroke(
                    id=str(uuid.uuid4())[:8],
                    source_type="skeleton",
                    points_px=list(edge),
                    closed=False,
                    is_hole=False,
                ))
        return strokes

    @staticmethod
    def _extract_closed_loops(graph: SkeletonGraph) -> list[Stroke]:
        """对无端点的连通域提取闭环 Stroke。

        规则：edge 首尾均不在 endpoint 集合中 → 闭环。
        """
        strokes: list[Stroke] = []
        ep_set: set[tuple[int, int]] = set(
            (int(ep.x), int(ep.y)) for ep in graph.endpoints
        )

        for edge in graph.edges:
            if len(edge) < 3:
                continue
            first = (int(edge[0].x), int(edge[0].y))
            last = (int(edge[-1].x), int(edge[-1].y))
            if first not in ep_set and last not in ep_set:
                strokes.append(Stroke(
                    id=str(uuid.uuid4())[:8],
                    source_type="skeleton",
                    points_px=list(edge),
                    closed=True,
                    is_hole=False,
                ))
        return strokes

    # ---- 排序与合并 ----

    @staticmethod
    def _order_strokes(strokes: list[Stroke]) -> list[Stroke]:
        """确定性排序：按 bounding box 中心 (y, x)。"""
        def _bbox_center(s: Stroke) -> tuple[float, float]:
            min_x = min(p.x for p in s.points_px)
            max_x = max(p.x for p in s.points_px)
            min_y = min(p.y for p in s.points_px)
            max_y = max(p.y for p in s.points_px)
            cy = (min_y + max_y) * 0.5
            cx = (min_x + max_x) * 0.5
            return (cy, cx)

        return sorted(strokes, key=_bbox_center)

    @staticmethod
    def _merge_nearby_endpoints(
        strokes: list[Stroke],
        threshold_px: float = 0.0,
    ) -> list[Stroke]:
        """附近端点合并 — 轻量预留。

        threshold_px=0 时不启用，直接返回原列表。
        """
        if threshold_px <= 0 or len(strokes) < 2:
            return strokes
        # 预留：后续可实现基于距离的端点合并
        return strokes

    # ---- debug 输出 ----

    @staticmethod
    def save_debug_graph(
        binary: np.ndarray,
        skeleton: np.ndarray,
        graph: SkeletonGraph,
        output_path: str,
    ) -> str:
        """保存骨架图调试 PNG。

        左=原始二值图, 右=骨架叠加图 (端点=红圈, 分叉点=蓝圈, 边=随机色)。
        """
        h, w = binary.shape[:2]
        vis = np.zeros((h, w * 2, 3), dtype=np.uint8)

        left = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        vis[:, :w] = left

        right = np.zeros((h, w, 3), dtype=np.uint8)
        right[:, :, 2] = binary
        right[:, :, 1] = skeleton

        be_used = graph.stats.get("skeleton_backend_used", "?")
        info = (f'backend={be_used} '
                f'ep={len(graph.endpoints)} bp={len(graph.branchpoints)}')
        cv2.putText(right, info, (5, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cv2.putText(right, f'comp={len(graph.components)} edge={len(graph.edges)}',
                    (5, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        for ep in graph.endpoints:
            cv2.circle(right, (int(ep.x), int(ep.y)), 3, (0, 0, 255), -1)
        for bp in graph.branchpoints:
            cv2.circle(right, (int(bp.x), int(bp.y)), 4, (255, 0, 0), -1)

        import random
        random.seed(42)
        for edge in graph.edges:
            color = (random.randint(64, 255), random.randint(64, 255), random.randint(64, 255))
            for px in edge:
                cv2.circle(right, (int(px.x), int(px.y)), 1, color, -1)

        vis[:, w:] = right
        cv2.line(vis, (w, 0), (w, h), (128, 128, 128), 2)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, vis)
        return output_path

    @staticmethod
    def save_debug_strokes(
        binary: np.ndarray,
        skeleton: np.ndarray,
        strokes: list[Stroke],
        output_path: str,
    ) -> str:
        """保存骨架 Stroke 调试图 PNG。

        左=原始二值图, 右=Stroke 叠加图 (不同颜色 + 首点绿圈/末点红叉 + stroke id 标注)。
        """
        h, w = binary.shape[:2]
        vis = np.zeros((h, w * 2, 3), dtype=np.uint8)

        left = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        vis[:, :w] = left

        right = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        # 半透明叠骨架
        right[:, :, 1] = np.clip(right[:, :, 1].astype(np.int32) + (skeleton // 2).astype(np.int32), 0, 255).astype(np.uint8)

        pal = [
            (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
            (255, 0, 255), (0, 255, 255), (128, 255, 0), (255, 128, 0),
            (0, 128, 255), (128, 0, 255), (255, 255, 128), (128, 255, 255),
        ]
        for i, stroke in enumerate(strokes):
            color = pal[i % len(pal)]
            for p in stroke.points_px:
                cv2.circle(right, (int(p.x), int(p.y)), 1, color, -1)

            # 标注 stroke id 和方向
            if len(stroke.points_px) >= 1:
                first = stroke.points_px[0]
                cv2.circle(right, (int(first.x), int(first.y)), 4, (0, 255, 0), -1)
                label = f"{i}:{stroke.id}"
                cv2.putText(right, label, (int(first.x) + 5, int(first.y) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
            if len(stroke.points_px) >= 2:
                last = stroke.points_px[-1]
                cv2.drawMarker(right, (int(last.x), int(last.y)), (0, 0, 255),
                               cv2.MARKER_CROSS, 6, 1)

            if stroke.closed:
                cx = int(sum(p.x for p in stroke.points_px) / max(len(stroke.points_px), 1))
                cy = int(sum(p.y for p in stroke.points_px) / max(len(stroke.points_px), 1))
                cv2.putText(right, "(closed)", (cx - 20, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

        info = f'strokes={len(strokes)} closed={sum(1 for s in strokes if s.closed)}'
        cv2.putText(right, info, (5, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        vis[:, w:] = right
        cv2.line(vis, (w, 0), (w, h), (128, 128, 128), 2)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, vis)
        return output_path
