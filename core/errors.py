class WeldingError(Exception):
    """焊接/绘图管线异常基类"""
    pass


class MappingError(WeldingError):
    """空间映射异常（UV映射失败、坐标系转换错误）"""
    pass


class WorkplaneError(MappingError):
    """工作空间标定异常（如三点共线、平面退化）"""
    pass


class PathExtractionError(WeldingError):
    """路径提取异常（轮廓/骨架提取失败）"""
    pass


class ConfigurationError(WeldingError):
    """配置异常（缺失字段、非法参数值）"""
    pass
