class WeldingError(Exception):
    """焊接/绘图管线异常基类"""
    pass


class WorkplaneError(WeldingError):
    """工作空间标定异常（如三点共线）"""
    pass
