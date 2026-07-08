# -*- coding: utf-8 -*-
"""
IP 和 Token 统计模块
用于记录每个 IP 地址的访问情况和 Token 消耗
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict


def _safe_fromisoformat(ts: str) -> datetime:
    """兼容 Python 3.10/3.11 的 ISO 时间解析（去掉时区后缀）"""
    if not ts:
        return datetime.min
    # 去掉 'Z' 后缀（Python 3.11 不支持）
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    # 处理 '+00:00' 等时区信息——3.11 直接解析会抛异常
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        # 去掉时区部分
        if '+' in ts:
            ts = ts.split('+')[0]
        elif 'Z' in ts:
            ts = ts.replace('Z', '')
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.min


class TokenStatsManager:
    """Token 和 IP 统计管理器"""
    
    def __init__(self, stats_file: str = "token_stats.json"):
        self.stats_file = stats_file
        self.stats = self._load_stats()
    
    def _load_stats(self) -> Dict:
        """加载统计文件"""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[TokenStats] 加载统计文件失败: {e}")
                return {"records": []}
        return {"records": []}
    
    def _save_stats(self):
        """保存统计文件"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TokenStats] 保存统计文件失败: {e}")
    
    def record_usage(
        self,
        ip: str,
        endpoint: str,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        model: str = "",
        status: str = "success",
        error_message: str = ""
    ):
        """
        记录一次 API 调用
        
        Args:
            ip: 客户端 IP 地址
            endpoint: API 端点
            provider: 模型提供商 (deepseek, aliyun)
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            total_tokens: 总 token 数
            model: 模型名称
            status: 状态 (success, error)
            error_message: 错误信息
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "ip": ip,
            "endpoint": endpoint,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "status": status,
            "error_message": error_message
        }
        
        self.stats["records"].append(record)
        self._save_stats()
    
    def get_stats_by_ip(self, ip: Optional[str] = None, days: int = 30) -> Dict:
        """
        获取按 IP 统计的数据
        
        Args:
            ip: 指定 IP (None 表示所有 IP)
            days: 最近多少天的数据
        
        Returns:
            统计字典
        """
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        
        # 过滤时间范围内的记录
        filtered_records = []
        for record in self.stats["records"]:
            try:
                record_time = _safe_fromisoformat(record["timestamp"]).timestamp()
                if record_time >= cutoff_time:
                    filtered_records.append(record)
            except:
                continue
        
        # 按 IP 分组统计
        ip_stats = defaultdict(lambda: {
            "total_requests": 0,
            "success_requests": 0,
            "error_requests": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "providers": defaultdict(int),
            "endpoints": defaultdict(int),
            "first_seen": None,
            "last_seen": None
        })
        
        for record in filtered_records:
            ip_addr = record["ip"]
            stats = ip_stats[ip_addr]
            
            # 如果指定了 IP，只统计该 IP
            if ip and ip_addr != ip:
                continue
            
            stats["total_requests"] += 1
            if record["status"] == "success":
                stats["success_requests"] += 1
            else:
                stats["error_requests"] += 1
            
            stats["total_tokens"] += record.get("total_tokens", 0)
            stats["prompt_tokens"] += record.get("prompt_tokens", 0)
            stats["completion_tokens"] += record.get("completion_tokens", 0)
            
            stats["providers"][record.get("provider", "unknown")] += 1
            stats["endpoints"][record.get("endpoint", "unknown")] += 1
            
            timestamp = record.get("timestamp")
            if timestamp:
                if stats["first_seen"] is None or timestamp < stats["first_seen"]:
                    stats["first_seen"] = timestamp
                if stats["last_seen"] is None or timestamp > stats["last_seen"]:
                    stats["last_seen"] = timestamp
        
        return dict(ip_stats)
    
    def get_all_stats(self, days: int = 30) -> Dict:
        """
        获取总体统计信息
        
        Args:
            days: 最近多少天的数据
        
        Returns:
            总体统计字典
        """
        ip_stats = self.get_stats_by_ip(days=days)
        
        # 汇总所有 IP 的数据
        total_stats = {
            "total_requests": 0,
            "success_requests": 0,
            "error_requests": 0,
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "unique_ips": len(ip_stats),
            "providers": defaultdict(int),
            "endpoints": defaultdict(int)
        }
        
        for ip, stats in ip_stats.items():
            total_stats["total_requests"] += stats["total_requests"]
            total_stats["success_requests"] += stats["success_requests"]
            total_stats["error_requests"] += stats["error_requests"]
            total_stats["total_tokens"] += stats["total_tokens"]
            total_stats["prompt_tokens"] += stats["prompt_tokens"]
            total_stats["completion_tokens"] += stats["completion_tokens"]
            
            for provider, count in stats["providers"].items():
                total_stats["providers"][provider] += count
            
            for endpoint, count in stats["endpoints"].items():
                total_stats["endpoints"][endpoint] += count
        
        # 转换 defaultdict 为普通 dict
        total_stats["providers"] = dict(total_stats["providers"])
        total_stats["endpoints"] = dict(total_stats["endpoints"])
        
        return {
            "summary": total_stats,
            "ip_details": ip_stats
        }
    
    def get_recent_records(self, limit: int = 100, days: int = 7) -> List[Dict]:
        """
        获取最近的调用记录
        
        Args:
            limit: 返回记录数量限制
            days: 最近多少天的数据
        
        Returns:
            记录列表
        """
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        
        recent_records = []
        for record in self.stats["records"]:
            try:
                record_time = _safe_fromisoformat(record["timestamp"]).timestamp()
                if record_time >= cutoff_time:
                    recent_records.append(record)
            except:
                continue
        
        # 按时间倒序
        recent_records.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return recent_records[:limit]
    
    def clear_old_records(self, days: int = 90):
        """
        清理旧记录
        
        Args:
            days: 保留最近多少天的数据
        """
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        
        original_count = len(self.stats["records"])
        self.stats["records"] = [
            record for record in self.stats["records"]
            if _safe_fromisoformat(record["timestamp"]).timestamp() >= cutoff_time
        ]
        
        removed_count = original_count - len(self.stats["records"])
        if removed_count > 0:
            self._save_stats()
            print(f"[TokenStats] 清理了 {removed_count} 条旧记录")
        
        return removed_count


# 全局单例
token_stats_manager = TokenStatsManager()
