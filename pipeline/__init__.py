"""焊接/绘图轨迹生成管线 — 纯 Python 模块，无 Qt/PySide6 依赖"""

from pipeline.font_renderer import render_char, render_text, get_default_font_path
from pipeline.skeleton_extractor import extract_paths
from pipeline.layout_engine import layout_text
from pipeline.path_processor import process_paths
from pipeline.workplane_mapper import compute_workplane, map_to_3d
from pipeline.weld_path_planner import plan_weld_paths
from pipeline.pen_process import plan_pen_motion
from pipeline.trajectory_planner import plan_trajectory
from pipeline.file_output import write_weld_txt, write_weld_json, make_output_paths
from pipeline.preview import preview_paths_2d, preview_weld_segments, preview_pen_segments
