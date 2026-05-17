"""轮廓字引擎 — PIL 二值图 → cv2.findContours → Stroke 序列

焊接文字请经 pipeline.text_stroke_extract.extract_glyph_strokes(..., mode="contour")
调用，勿与骨架模式混用。图片模式见 image_preprocessor。

无 Qt/PySide6 依赖。只做像素空间轮廓提取 + 可选像素级简化。
不做 mm 映射、不做 mm 级重采样、不做拐角保护、不做工艺段。
"""

from pathlib import Path

import cv2
import numpy as np

from core.types import PixelPoint, Stroke, PathConfig


# 轮廓面积过滤默认值（px²）。仅用于噪声剔除，不做语义级路径长度过滤。
# 2x2 px 正方形的面积 = 4.0，足以过滤单像素/双像素噪点。
# 对 600px 渲染的 O/0/8 内轮廓（数千 px²）有 500x+ 安全裕度。
DEFAULT_MIN_CONTOUR_AREA_PX: float = 4.0


class ContourExtractor:
    """从二值图中提取轮廓并输出 Stroke 序列。

    用法:
        ext = ContourExtractor()
        strokes = ext.extract(binary, config)
    """

    def extract(
        self,
        binary: np.ndarray,
        config: PathConfig | None = None,
        simplify: bool = False,
        *,
        px_per_mm: float | None = None,
        min_area_px: float | None = None,
    ) -> list[Stroke]:
        """主入口：二值图 → Stroke 列表。

        Args:
            binary: 二值 numpy 数组 (dtype=uint8, 0=背景, 255=前景)
            config: 路径配置，None 则用默认 PathConfig
            simplify: 是否启用像素级轮廓简化（默认 False，保持 Part 2.2 行为）
            px_per_mm: 像素/mm 换算比。用于从 PathConfig.min_path_length_mm
                       推导 min_area_px。不传则使用保守默认值。
            min_area_px: 轮廓最小像素面积。优先级最高。
                         直接传给 _filter_small，不做额外转换。

        Returns:
            list[Stroke]: 按 boundingRect X 排序的轮廓 stroke
        """
        cfg = config or PathConfig()
        raw_contours, hierarchy = self._find_contours(binary)

        if raw_contours is None or len(raw_contours) == 0:
            return []

        # 确定 min_area_px（像素面积）
        # 优先级: min_area_px 显式 > px_per_mm 推导 > 保守默认
        if min_area_px is not None:
            effective_min_area = min_area_px
        elif px_per_mm is not None and px_per_mm > 0:
            min_len_px = cfg.min_path_length_mm * px_per_mm
            # 长度→面积: 假设轮廓最小包围盒边长 ≈ min_len_px / 4
            effective_min_area = max(
                DEFAULT_MIN_CONTOUR_AREA_PX,
                (min_len_px / 4.0) ** 2,
            )
        else:
            effective_min_area = DEFAULT_MIN_CONTOUR_AREA_PX

        raw_contours, hierarchy = self._filter_small(
            raw_contours, hierarchy, effective_min_area,
        )

        if len(raw_contours) == 0:
            return []

        # 可选：像素级简化
        if simplify:
            contours = []
            for cnt in raw_contours:
                simplified = self._simplify_contour_vertices(
                    cnt, max_vertices=cfg.contour_max_vertices,
                )
                contours.append(simplified)
        else:
            contours = raw_contours

        # 内外轮廓分类
        labels = self._classify_inner_outer(hierarchy)

        # 转换为 Stroke
        # 用原始轮廓检测闭合状态，避免 approxPolyDP 简化后首尾不重合导致 closed 丢失
        strokes = []
        for i, cnt in enumerate(contours):
            is_hole = labels[i] == "inner"
            was_closed = ContourExtractor._detect_closed(raw_contours[i])
            stroke = self._extract_contour_path(cnt, is_hole=is_hole, force_closed=was_closed)
            strokes.append(stroke)

        # 外轮廓 CCW / 内轮廓 CW
        strokes = self._unify_direction(strokes, contours)

        # 按 boundingRect X 排序
        strokes.sort(key=lambda s: min(p.x for p in s.points_px))

        return strokes

    # ---- 内部方法 ----

    @staticmethod
    def _find_contours(binary: np.ndarray) -> tuple[list, np.ndarray | None]:
        """cv2.findContours 包装。

        使用 RETR_TREE 获取完整层级关系，CHAIN_APPROX_NONE 保留全部点。
        """
        # 确保是 uint8 二值图
        if binary.dtype != np.uint8:
            binary = binary.astype(np.uint8)
        # 确保前景=255 背景=0（cv2.findContours 期望白色前景）
        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE,
        )
        if hierarchy is not None:
            hierarchy = hierarchy[0]  # (1, N, 4) → (N, 4)
        return contours, hierarchy

    @staticmethod
    def _filter_small(
        contours: list,
        hierarchy: np.ndarray | None,
        min_area_px: float,
    ) -> tuple[list, np.ndarray | None]:
        """过滤小轮廓（面积 < min_area_px）。"""
        if hierarchy is None:
            keep = [i for i, cnt in enumerate(contours) if cv2.contourArea(cnt) >= min_area_px]
        else:
            keep = [i for i, cnt in enumerate(contours) if cv2.contourArea(cnt) >= min_area_px]

        if len(keep) == len(contours):
            return contours, hierarchy

        filtered = [contours[i] for i in keep]
        if hierarchy is not None:
            filtered_h = hierarchy[keep]
        else:
            filtered_h = None
        return filtered, filtered_h

    @staticmethod
    def _classify_inner_outer(hierarchy: np.ndarray | None) -> list[str]:
        """根据 hierarchy 分类每个轮廓为 "outer" 或 "inner"。

        hierarchy[i] = [next, prev, first_child, parent]
        parent == -1 → 顶层外轮廓 (outer)
        parent != -1 → 内轮廓/孔洞 (inner)

        Returns:
            list[str]: 每项为 "outer" 或 "inner"
        """
        if hierarchy is None or len(hierarchy) == 0:
            return ["outer"] * len(hierarchy) if hierarchy is not None else []

        labels = []
        for h in hierarchy:
            parent = h[3]
            if parent == -1:
                labels.append("outer")
            else:
                labels.append("inner")
        return labels

    @staticmethod
    def _detect_closed(contour: np.ndarray, threshold_px: float = 2.0) -> bool:
        """检测 OpenCV contour 是否闭合（首尾距离 < threshold）。"""
        if len(contour) < 3:
            return False
        first = contour[0][0]
        last = contour[-1][0]
        dx = float(first[0]) - float(last[0])
        dy = float(first[1]) - float(last[1])
        return (dx * dx + dy * dy) < (threshold_px * threshold_px)

    @staticmethod
    def _extract_contour_path(
        contour: np.ndarray,
        is_hole: bool = False,
        glyph_id: str | None = None,
        force_closed: bool | None = None,
    ) -> Stroke:
        """将 OpenCV contour 转换为 Stroke。

        contour shape: (N, 1, 2) from CHAIN_APPROX_NONE

        Args:
            force_closed: 如果非 None，直接使用此值作为 closed，不重新检测。
                          用于简化后保留原始闭合状态。
        """
        pts = contour.squeeze(1)  # (N, 1, 2) → (N, 2)
        if pts.ndim == 1:
            pts = pts.reshape(1, 2)

        pixels = [PixelPoint(x=float(p[0]), y=float(p[1])) for p in pts]

        if force_closed is not None:
            closed = force_closed
        else:
            closed = ContourExtractor._detect_closed(contour)

        import uuid
        return Stroke(
            id=str(uuid.uuid4())[:8],
            source_type="contour",
            points_px=pixels,
            closed=closed,
            is_hole=is_hole,
            glyph_id=glyph_id,
        )

    @staticmethod
    def _unify_direction(
        strokes: list[Stroke],
        contours: list[np.ndarray],
    ) -> list[Stroke]:
        """统一轮廓方向：外轮廓 CCW（正面积），内轮廓 CW（负面积）。

        OpenCV 默认外轮廓 CCW、内轮廓 CW，但 CHAIN_APPROX_NONE
        可能不保证方向。此处确保方向一致。
        """
        for i, stroke in enumerate(strokes):
            cnt = contours[i]
            area = cv2.contourArea(cnt)
            if stroke.is_hole:
                if area > 0:
                    stroke.points_px.reverse()
            else:
                if area < 0:
                    stroke.points_px.reverse()
        return strokes

    # ---- 像素级轮廓简化（可选，轻量预处理） ----

    @staticmethod
    def _simplify_contour_vertices(
        contour: np.ndarray,
        max_vertices: int = 12,
    ) -> np.ndarray:
        """approxPolyDP + 二分 epsilon 控制最大顶点数。

        Args:
            contour: OpenCV contour (N, 1, 2)
            max_vertices: 最大顶点数

        Returns:
            simplified contour in same (N, 1, 2) format，最少 4 点
        """
        original_len = len(contour)
        arc_len = cv2.arcLength(contour, True)

        if arc_len <= 0 or original_len <= max_vertices:
            return contour

        lo, hi = 0.0, arc_len
        best = contour
        for _ in range(20):  # 二分迭代
            mid = (lo + hi) * 0.5
            approx = cv2.approxPolyDP(contour, mid, True)
            nv = len(approx)
            if nv <= max_vertices:
                best = approx
                hi = mid
            else:
                lo = mid
            if hi - lo < 1e-4:
                break

        # 确保最少 4 点（闭合轮廓最少四边形）
        if len(best) < 4 and len(contour) >= 4:
            return cv2.approxPolyDP(contour, 0.0, True)

        return best

    @staticmethod
    def _adaptive_simplify_closed(
        contour: np.ndarray,
        config: PathConfig,
    ) -> np.ndarray:
        """对闭合轮廓做像素级自适应简化（轻量版）。

        当前 Part 只做 approxPolyDP 顶点数限制。
        完整的直/曲线分类、弦偏差判断留给 Phase 4 PathRefinement。
        """
        return ContourExtractor._simplify_contour_vertices(
            contour, max_vertices=config.contour_max_vertices,
        )

    # ---- debug 输出 ----

    @staticmethod
    def save_debug_overlay(
        binary: np.ndarray,
        strokes: list[Stroke],
        output_path: str,
    ) -> str:
        """保存轮廓叠加调试图片。

        外轮廓=绿色, 内轮廓=红色, stroke id 标注。

        Args:
            binary: 原始二值图
            strokes: Stroke 列表
            output_path: 输出 PNG 路径

        Returns:
            输出文件路径
        """
        # 转 BGR 彩色
        if binary.ndim == 2:
            vis = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        else:
            vis = binary.copy()

        for i, stroke in enumerate(strokes):
            color = (0, 0, 255) if stroke.is_hole else (0, 255, 0)  # 红=内, 绿=外
            pts = np.array(
                [[int(p.x), int(p.y)] for p in stroke.points_px],
                dtype=np.int32,
            ).reshape(-1, 1, 2)
            cv2.drawContours(vis, [pts], -1, color, 2)

            # 标注 stroke id 和类型
            cx = int(sum(p.x for p in stroke.points_px) / max(len(stroke.points_px), 1))
            cy = int(sum(p.y for p in stroke.points_px) / max(len(stroke.points_px), 1))
            label = f"{stroke.id}"
            cv2.putText(vis, label, (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, vis)
        return output_path

    @staticmethod
    def save_debug_compare(
        binary: np.ndarray,
        raw_strokes: list[Stroke],
        simplified_strokes: list[Stroke],
        output_path: str,
    ) -> str:
        """保存简化前后对比图。

        左半=原始轮廓(蓝线), 右半=简化后轮廓(绿线), 标注点数。

        Args:
            binary: 原始二值图
            raw_strokes: 原始 Stroke
            simplified_strokes: 简化后 Stroke
            output_path: 输出 PNG 路径

        Returns:
            输出文件路径
        """
        h, w = binary.shape[:2]
        vis = np.zeros((h, w * 2, 3), dtype=np.uint8)

        # 左半：原始
        left = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        for s in raw_strokes:
            color = (255, 0, 0)  # 蓝
            pts = np.array([[int(p.x), int(p.y)] for p in s.points_px],
                           dtype=np.int32).reshape(-1, 1, 2)
            cv2.drawContours(left, [pts], -1, color, 1)
            cv2.putText(left, f'{s.id}:{len(s.points_px)}',
                        (int(s.points_px[0].x), int(s.points_px[0].y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        vis[:, :w] = left

        # 右半：简化
        right = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        for s in simplified_strokes:
            color = (0, 255, 0)  # 绿
            pts = np.array([[int(p.x), int(p.y)] for p in s.points_px],
                           dtype=np.int32).reshape(-1, 1, 2)
            cv2.drawContours(right, [pts], -1, color, 1)
            cv2.putText(right, f'{s.id}:{len(s.points_px)}',
                        (int(s.points_px[0].x), int(s.points_px[0].y)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
        vis[:, w:] = right

        # 分隔线
        cv2.line(vis, (w, 0), (w, h), (128, 128, 128), 2)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(output_path, vis)
        return output_path
