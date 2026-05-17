"""焊接/绘图 Pipeline 默认配置"""

from core.types import (
    RobotPoint,
    TextLayoutConfig,
    PathConfig,
    WorkspaceConfig,
    WeldingProcessConfig,
    ExportConfig,
)

# ---- 文字排版默认值 ----

DEFAULT_TEXT_CONFIG = TextLayoutConfig()

# ---- 路径提取与整形默认值 ----

DEFAULT_PATH_CONFIG = PathConfig()

# ---- 工作空间标定默认值 ----
# 注意：left_top/left_bottom/right_top 需要在运行时由用户标定或 CLI 参数填入，
# 以下仅提供除三点坐标之外的默认值。

DEFAULT_WORKSPACE_CONFIG = WorkspaceConfig()

# ---- 焊接工艺默认值 ----

DEFAULT_WELDING_CONFIG = WeldingProcessConfig()

# ---- 导出默认值 ----

DEFAULT_EXPORT_CONFIG = ExportConfig()


# ---- 旧版兼容常量（保留，供 ortho legacy 模式参考） ----
# 新 pipeline 主线不应依赖这些值。仅在 mapping_mode="ortho" 时可用作回退。

LEGACY_CHAR_HEIGHT_MM = 20.0
LEGACY_CHAR_SPACING_MM = 2.0
LEGACY_LINE_SPACING_MM = 5.0
LEGACY_LEAD_IN_MM = 3.0
LEGACY_LEAD_OUT_MM = 3.0
LEGACY_OVERLAP_MM = 5.0
LEGACY_POINT_SPACING_MM = 0.5
LEGACY_Z_SAFE = 166.0
LEGACY_Z_WORK = 156.5

# 旧名别名（向后兼容 app/pages/welding_page.py, services/welding_service.py）
CHAR_HEIGHT_MM = LEGACY_CHAR_HEIGHT_MM
CHAR_SPACING_MM = LEGACY_CHAR_SPACING_MM
LINE_SPACING_MM = LEGACY_LINE_SPACING_MM
MARGIN_LEFT_MM = 0.0
MARGIN_TOP_MM = 0.0
LEAD_IN_MM = LEGACY_LEAD_IN_MM
LEAD_OUT_MM = LEGACY_LEAD_OUT_MM
OVERLAP_MM = LEGACY_OVERLAP_MM
POINT_SPACING_MM = LEGACY_POINT_SPACING_MM
