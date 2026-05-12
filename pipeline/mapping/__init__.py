"""Phase 5: Workspace UV Mapping — 像素→工作平面→机器人坐标

WorkPlane: 三点定义倾斜工作平面 + UV/法向映射
PoseMapper: 批量 Stroke 坐标映射
只做位置映射；工具姿态固定沿用 orientation_source。
"""

from pipeline.mapping.workplane import WorkPlane
from pipeline.mapping.pose_mapper import PoseMapper
