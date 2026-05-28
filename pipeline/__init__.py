"""焊接/绘图轨迹生成管线 — 纯 Python 模块，无 Qt/PySide6 依赖"""

from pipeline.raster import (
    FontRasterizer, LineboxGlyph,
    render_char, render_text,
    render_char_in_linebox, render_text_linebox,
    get_default_font_path,
)

_OPTIONAL_IMPORT_ERRORS = {}

try:
    from pipeline.vision import ContourExtractor
except ImportError as exc:
    ContourExtractor = None
    _OPTIONAL_IMPORT_ERRORS["ContourExtractor"] = exc

try:
    from pipeline.vision import SkeletonExtractor, SkeletonGraph
except ImportError as exc:
    SkeletonExtractor = None
    SkeletonGraph = None
    _OPTIONAL_IMPORT_ERRORS["SkeletonExtractor"] = exc

try:
    from pipeline.skeleton_extractor import extract_paths
except ImportError as exc:
    extract_paths = None
    _OPTIONAL_IMPORT_ERRORS["extract_paths"] = exc

try:
    from pipeline.layout_engine import layout_text
except ImportError as exc:
    layout_text = None
    _OPTIONAL_IMPORT_ERRORS["layout_text"] = exc

try:
    from pipeline.path_processor import process_paths
except ImportError as exc:
    process_paths = None
    _OPTIONAL_IMPORT_ERRORS["process_paths"] = exc

try:
    from pipeline.workplane_mapper import compute_workplane, map_to_3d
except ImportError as exc:
    compute_workplane = None
    map_to_3d = None
    _OPTIONAL_IMPORT_ERRORS["workplane_mapper"] = exc

try:
    from pipeline.weld_path_planner import plan_weld_paths
except ImportError as exc:
    plan_weld_paths = None
    _OPTIONAL_IMPORT_ERRORS["plan_weld_paths"] = exc

try:
    from pipeline.trajectory_planner import plan_trajectory
except ImportError as exc:
    plan_trajectory = None
    _OPTIONAL_IMPORT_ERRORS["plan_trajectory"] = exc

try:
    from pipeline.file_output import write_weld_txt, write_weld_json, make_output_paths
except ImportError as exc:
    write_weld_txt = None
    write_weld_json = None
    make_output_paths = None
    _OPTIONAL_IMPORT_ERRORS["file_output"] = exc

try:
    from pipeline.preview import preview_paths_2d, preview_weld_segments
except ImportError as exc:
    preview_paths_2d = None
    preview_weld_segments = None
    _OPTIONAL_IMPORT_ERRORS["preview"] = exc


def get_optional_import_errors():
    return dict(_OPTIONAL_IMPORT_ERRORS)
