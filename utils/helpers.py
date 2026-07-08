"""小型工具函数模块"""
from datetime import datetime


def get_current_datetime():
    """获取当前时间字符串，格式：YYYYMMDDHHmmSS"""
    now = datetime.now()
    return now.strftime("%Y%m%d%H%M%S")
