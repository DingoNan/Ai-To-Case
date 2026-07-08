# -*- coding: utf-8 -*-
"""
Token 统计功能测试脚本
用于验证统计功能是否正常工作
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"

def test_stats_api():
    """测试统计 API"""
    print("=" * 60)
    print("Token 统计功能测试")
    print("=" * 60)
    
    # 1. 测试获取总体统计
    print("\n1. 测试获取总体统计 (GET /api/stats/summary)")
    try:
        response = requests.get(f"{BASE_URL}/api/stats/summary?days=30")
        data = response.json()
        print(f"   状态码: {response.status_code}")
        print(f"   成功: {data.get('success')}")
        if data.get('success'):
            summary = data.get('summary', {})
            print(f"   总请求数: {summary.get('total_requests', 0)}")
            print(f"   总 Token: {summary.get('total_tokens', 0)}")
            print(f"   唯一 IP: {summary.get('unique_ips', 0)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 2. 测试获取 IP 列表
    print("\n2. 测试获取 IP 列表 (GET /api/stats/ip-list)")
    try:
        response = requests.get(f"{BASE_URL}/api/stats/ip-list?days=30")
        data = response.json()
        print(f"   状态码: {response.status_code}")
        print(f"   成功: {data.get('success')}")
        if data.get('success'):
            print(f"   IP 数量: {data.get('total_ips', 0)}")
            ip_list = data.get('ip_list', [])
            if ip_list:
                print(f"   第一个 IP: {ip_list[0].get('ip')}")
                print(f"   请求数: {ip_list[0].get('total_requests', 0)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 3. 测试获取最近记录
    print("\n3. 测试获取最近记录 (GET /api/stats/recent)")
    try:
        response = requests.get(f"{BASE_URL}/api/stats/recent?limit=10&days=7")
        data = response.json()
        print(f"   状态码: {response.status_code}")
        print(f"   成功: {data.get('success')}")
        if data.get('success'):
            print(f"   记录数: {data.get('total', 0)}")
            records = data.get('records', [])
            if records:
                latest = records[0]
                print(f"   最新记录:")
                print(f"     时间: {latest.get('timestamp')}")
                print(f"     IP: {latest.get('ip')}")
                print(f"     端点: {latest.get('endpoint')}")
                print(f"     Token: {latest.get('total_tokens', 0)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 4. 测试统计页面
    print("\n4. 测试统计页面 (GET /stats)")
    try:
        response = requests.get(f"{BASE_URL}/stats")
        print(f"   状态码: {response.status_code}")
        print(f"   页面大小: {len(response.text)} 字节")
        if response.status_code == 200:
            print("   ✓ 页面可访问")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    # 5. 测试清理旧数据
    print("\n5. 测试清理旧数据 (POST /api/stats/clear)")
    try:
        response = requests.post(
            f"{BASE_URL}/api/stats/clear",
            json={"days": 90},
            headers={"Content-Type": "application/json"}
        )
        data = response.json()
        print(f"   状态码: {response.status_code}")
        print(f"   成功: {data.get('success')}")
        if data.get('success'):
            print(f"   清理记录数: {data.get('removed_count', 0)}")
    except Exception as e:
        print(f"   ❌ 失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


def test_generate_with_stats():
    """测试生成测试用例并查看统计"""
    print("\n\n" + "=" * 60)
    print("测试生成测试用例并记录统计")
    print("=" * 60)
    
    # 调用测试用例生成 API
    print("\n调用测试用例生成 API...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/testcase/generate/stream",
            json={
                "requirement_text": "用户登录功能，支持用户名密码登录",
                "test_module": "登录模块",
                "test_case_count": 3,
                "provider": "azure"
            },
            headers={"Content-Type": "application/json"}
        )
        
        print(f"状态码: {response.status_code}")
        print("注意: 流式响应需要特殊处理，这里只检查连接")
        
    except Exception as e:
        print(f"❌ 失败: {e}")
    
    # 查看统计是否更新
    print("\n查看统计更新...")
    try:
        response = requests.get(f"{BASE_URL}/api/stats/summary?days=1")
        data = response.json()
        if data.get('success'):
            summary = data.get('summary', {})
            print(f"总请求数: {summary.get('total_requests', 0)}")
            print(f"总 Token: {summary.get('total_tokens', 0)}")
    except Exception as e:
        print(f"❌ 失败: {e}")


if __name__ == "__main__":
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标服务: {BASE_URL}\n")
    
    # 先检查服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✓ 服务正常运行\n")
            test_stats_api()
            
            # 询问是否测试生成功能
            print("\n是否测试生成测试用例功能? (y/n)")
            choice = input().strip().lower()
            if choice == 'y':
                test_generate_with_stats()
        else:
            print(f"❌ 服务异常，状态码: {response.status_code}")
            print("请先启动服务: python main.py")
    except Exception as e:
        print(f"❌ 无法连接到服务: {e}")
        print("请确保服务已启动: python main.py")
