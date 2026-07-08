# -*- coding: utf-8 -*-
"""
LLM API调用层 - 支持DeepSeek和阿里云DashScope(Qwen)
"""
import os
import json as json_lib
import aiohttp
import certifi
import ssl
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 通用环境变量
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

# AI API 超时设置（秒）- 大文档处理需要更长超时
AI_API_TIMEOUT = int(os.getenv("AI_API_TIMEOUT", "120"))

# DeepSeek配置
ds_api_key = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# 阿里云DashScope(Qwen)配置（OpenAI兼容模式）
aliyun_api_key = os.getenv("ALIYUN_API_KEY")
ALIYUN_MODEL = os.getenv("ALIYUN_MODEL", "qwen-plus")
ALIYUN_BASE_URL = os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


def _build_ssl_context():
    """创建SSL上下文"""
    return ssl.create_default_context(cafile=certifi.where())


async def _call_openai_compatible_api(
    base_url: str, api_key: str, model: str, prompt: str,
    system_prompt: str = "你是一名资深测试工程师", max_tokens: int = 16000
):
    """
    调用 OpenAI 兼容 API（非流式）
    返回结果中包含 _token_usage 字段
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_build_ssl_context())
        ) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    result = await response.json()
                    usage = result.get("usage", {})
                    result["_token_usage"] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "model": model
                    }
                    return result
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_openai_compatible_api_stream(
    base_url: str, api_key: str, model: str, prompt: str,
    system_prompt: str = "你是一名资深测试工程师", max_tokens: int = 16000
):
    """
    流式调用 OpenAI 兼容 API，逐块返回内容
    最后一个yield会包含 _token_usage 信息

    Yields:
        str: 每次返回的文本片段
        最后额外 yield {"_token_usage": {...}} 带token统计
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": True,
        "max_tokens": max_tokens,
        "stream_options": {"include_usage": True}  # 部分API支持在流中返回usage
    }
    url = base_url.rstrip("/") + "/chat/completions"
    token_usage = {}
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_build_ssl_context())
        ) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield {"error": f"API调用失败: {response.status}", "details": error_text}
                    return

                # 逐行读取 SSE 流
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]  # 去掉 "data: " 前缀
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json_lib.loads(data)
                            choices = chunk.get("choices", [])
                            # 提取usage信息（部分API会在流中返回）
                            if "usage" in chunk:
                                token_usage = {
                                    "prompt_tokens": chunk["usage"].get("prompt_tokens", 0),
                                    "completion_tokens": chunk["usage"].get("completion_tokens", 0),
                                    "total_tokens": chunk["usage"].get("total_tokens", 0),
                                    "model": model
                                }
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json_lib.JSONDecodeError:
                            continue
                        except (IndexError, KeyError, TypeError):
                            continue

                # 最后yield token_usage信息（如果API不支持流式usage，用空字典）
                yield {"_token_usage": token_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "model": model}}
    except Exception as e:
        yield {"error": f"API请求异常: {str(e)}"}


async def call_llm_api(prompt: str, provider: str | None = None, system_prompt: str = "你是一名资深测试工程师"):
    """
    通用非流式调用入口：支持 DeepSeek、阿里云DashScope(Qwen)
    provider: "deepseek" | "aliyun"
    """
    use_provider = (provider or LLM_PROVIDER or "deepseek").lower()

    if use_provider == "aliyun":
        if not aliyun_api_key:
            return {"error": "缺少 ALIYUN_API_KEY"}
        return await _call_openai_compatible_api(
            base_url=ALIYUN_BASE_URL,
            api_key=aliyun_api_key,
            model=ALIYUN_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        )
    # 默认DeepSeek
    if use_provider in ("deepseek", "ds"):
        if not ds_api_key:
            return {"error": "缺少 DEEPSEEK_API_KEY"}
        return await _call_openai_compatible_api(
            base_url=DEEPSEEK_BASE_URL,
            api_key=ds_api_key,
            model=DEEPSEEK_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=8192
        )
    return {"error": f"不支持的provider: {use_provider}，可选: deepseek, aliyun"}


async def call_llm_api_stream(prompt: str, provider: str | None = None, system_prompt: str = "你是一名资深测试工程师"):
    """
    流式通用调用入口：支持 DeepSeek、阿里云DashScope(Qwen)
    provider: "deepseek" | "aliyun"

    最后额外 yield {"_token_usage": {...}} 带token统计
    """
    use_provider = (provider or LLM_PROVIDER or "deepseek").lower()

    if use_provider == "aliyun":
        if not aliyun_api_key:
            yield {"error": "缺少 ALIYUN_API_KEY"}
            return
        async for chunk in _call_openai_compatible_api_stream(
            base_url=ALIYUN_BASE_URL,
            api_key=aliyun_api_key,
            model=ALIYUN_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk
        return

    # 默认DeepSeek
    if use_provider in ("deepseek", "ds"):
        if not ds_api_key:
            yield {"error": "缺少 DEEPSEEK_API_KEY"}
            return
        async for chunk in _call_openai_compatible_api_stream(
            base_url=DEEPSEEK_BASE_URL,
            api_key=ds_api_key,
            model=DEEPSEEK_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=8192
        ):
            yield chunk
        return

    yield {"error": f"不支持的provider: {use_provider}，可选: deepseek, aliyun"}


async def call_vision_api(image_base64: str, prompt: str, provider: str | None = None):
    """
    调用视觉大模型识别图片内容

    Args:
        image_base64: base64编码的图片数据
        prompt: 识别提示词
        provider: "aliyun" | "deepseek"，默认使用阿里云

    Returns:
        dict: API返回结果
    """
    use_provider = (provider or "aliyun").lower()

    if use_provider == "aliyun":
        if not aliyun_api_key:
            return {"error": "缺少 ALIYUN_API_KEY"}
        return await _call_aliyun_vision_api(image_base64, prompt)

    if use_provider == "deepseek":
        if not ds_api_key:
            return {"error": "缺少 DEEPSEEK_API_KEY"}
        return await _call_deepseek_vision_api(image_base64, prompt)

    return {"error": f"不支持的视觉模型provider: {use_provider}，可选: aliyun, deepseek"}


async def _call_aliyun_vision_api(image_base64: str, prompt: str):
    """调用阿里云通义千问视觉模型"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {aliyun_api_key}"
    }
    payload = {
        "model": "qwen-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = ALIYUN_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_build_ssl_context())
        ) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_deepseek_vision_api(image_base64: str, prompt: str):
    """调用DeepSeek视觉模型"""
    if not ds_api_key:
        return {"error": "缺少 DEEPSEEK_API_KEY"}

    vision_model = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-chat")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ds_api_key}"
    }
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=_build_ssl_context())
        ) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}
# -*- conding: utf-8 -*-
import os
import aiohttp
import certifi
import ssl
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 通用环境变量
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

# AI API 超时设置（秒）- 大文档处理需要更长超时
AI_API_TIMEOUT = int(os.getenv("AI_API_TIMEOUT", "120"))

# DeepSeek配置
ds_api_key = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# 阿里云DashScope(Qwen)配置（OpenAI兼容模式）
aliyun_api_key = os.getenv("ALIYUN_API_KEY")
ALIYUN_MODEL = os.getenv("ALIYUN_MODEL", "qwen-plus")
ALIYUN_BASE_URL = os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# 微软 Azure OpenAI 配置
azure_api_key = os.getenv("AZURE_API_KEY")
AZURE_BASE_URL = os.getenv("AZURE_BASE_URL")  # 形如 https://<resource>.openai.azure.com
AZURE_DEPLOYMENT = os.getenv("AZURE_DEPLOYMENT")  # 部署名
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "2024-08-01-preview")

# 字节跳动豆包配置（OpenAI兼容模式）
doubao_api_key = os.getenv("DOUBAO_API_KEY")
DOUBAO_MODEL = os.getenv("DOUBAO_MODEL", "doubao-1-5-pro-32k-250115")
DOUBAO_BASE_URL = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")


async def _call_openai_compatible_api(base_url: str, api_key: str, model: str, prompt: str, system_prompt: str = "你是一名资深测试工程师", max_tokens: int = 16000):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    result = await response.json()
                    # 提取 Token 信息
                    usage = result.get("usage", {})
                    result["_token_usage"] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "model": model
                    }
                    return result
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_openai_compatible_api_stream(base_url: str, api_key: str, model: str, prompt: str, system_prompt: str = "你是一名资深测试工程师", max_tokens: int=16000 ):
    """
    流式调用 OpenAI 兼容 API，逐块返回内容

    Yields:
        str: 每次返回的文本片段
    """
    import json as json_lib
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": True,
        "max_tokens": max_tokens
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield {"error": f"API调用失败: {response.status}", "details": error_text}
                    return

                # 逐行读取 SSE 流
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]  # 去掉 "data: " 前缀
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json_lib.loads(data)
                            choices = chunk.get("choices", [])
                            # 检查 choices 是否为空
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json_lib.JSONDecodeError:
                            continue
                        except (IndexError, KeyError, TypeError):
                            # 处理索引越界或键错误
                            continue
    except Exception as e:
        yield {"error": f"API请求异常: {str(e)}"}


async def _call_azure_openai_api(base_url: str, api_key: str, deployment: str, api_version: str, prompt: str, system_prompt: str = "你是一名资深测试工程师", max_tokens: int = 16000):
    if not base_url or not deployment:
        return {"error": "缺少 AZURE_BASE_URL 或 AZURE_DEPLOYMENT"}
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens
    }
    url = f"{base_url.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    result = await response.json()
                    # 提取 Token 信息
                    usage = result.get("usage", {})
                    result["_token_usage"] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                        "model": deployment
                    }
                    return result
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_azure_openai_api_stream(base_url: str, api_key: str, deployment: str, api_version: str, prompt: str, system_prompt: str = "你是一名资深测试工程师", max_tokens: int = 16000):
    """
    流式调用 Azure OpenAI API，逐块返回内容

    Yields:
        str: 每次返回的文本片段
    """
    import json as json_lib
    if not base_url or not deployment:
        yield {"error": "缺少 AZURE_BASE_URL 或 AZURE_DEPLOYMENT"}
        return
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "max_tokens": max_tokens
    }
    url = f"{base_url.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield {"error": f"API调用失败: {response.status}", "details": error_text}
                    return

                # 逐行读取 SSE 流
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]  # 去掉 "data: " 前缀
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json_lib.loads(data)
                            choices = chunk.get("choices", [])
                            # 检查 choices 是否为空
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json_lib.JSONDecodeError:
                            continue
                        except (IndexError, KeyError, TypeError):
                            # 处理索引越界或键错误
                            continue
    except Exception as e:
        yield {"error": f"API请求异常: {str(e)}"}



#  AI整理优化的调用
async def call_llm_api(prompt: str, provider: str | None = None, system_prompt: str = "你是一名资深测试工程师"):
    """
    通用调用入口：支持 DeepSeek、阿里云DashScope(Qwen)、Azure、豆包
    provider: "deepseek" | "aliyun" | "azure" | "microsoft" | "doubao"
    """
    use_provider = (provider or LLM_PROVIDER or "deepseek").lower()

    if use_provider == "aliyun":
        if not aliyun_api_key:
            return {"error": "缺少 ALIYUN_API_KEY"}
        return await _call_openai_compatible_api(
            base_url=ALIYUN_BASE_URL,
            api_key=aliyun_api_key,
            model=ALIYUN_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        )
    if use_provider in ("azure", "microsoft"):
        if not azure_api_key:
            return {"error": "缺少 AZURE_API_KEY"}
        return await _call_azure_openai_api(
            base_url=AZURE_BASE_URL,
            api_key=azure_api_key,
            deployment=AZURE_DEPLOYMENT,
            api_version=AZURE_API_VERSION,
            prompt=prompt,
            system_prompt=system_prompt,
        )
    if use_provider == "doubao":
        if not doubao_api_key:
            return {"error": "缺少 DOUBAO_API_KEY"}
        return await _call_openai_compatible_api(
            base_url=DOUBAO_BASE_URL,
            api_key=doubao_api_key,
            model=DOUBAO_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        )
    # 默认DeepSeek
    if not ds_api_key:
        return {"error": "缺少 DEEPSEEK_API_KEY"}
    return await _call_openai_compatible_api(
        base_url=DEEPSEEK_BASE_URL,
        api_key=ds_api_key,
        model=DEEPSEEK_MODEL,
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=8192
    )


async def call_llm_api_stream(prompt: str, provider: str | None = None, system_prompt: str = "你是一名资深测试工程师"):
    """
    流式通用调用入口：支持 DeepSeek、阿里云DashScope(Qwen)、Azure OpenAI、豆包
    provider: "deepseek" | "aliyun" | "azure" | "microsoft" | "doubao"

    Yields:
        str: 每次返回的文本片段
    """
    use_provider = (provider or LLM_PROVIDER or "deepseek").lower()
    if use_provider == "aliyun":
        if not aliyun_api_key:
            yield {"error": "缺少 ALIYUN_API_KEY"}
            return
        async for chunk in _call_openai_compatible_api_stream(
            base_url=ALIYUN_BASE_URL,
            api_key=aliyun_api_key,
            model=ALIYUN_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk
        return
    if use_provider in ("azure", "microsoft"):
        if not azure_api_key:
            yield {"error": "缺少 AZURE_API_KEY"}
            return
        async for chunk in _call_azure_openai_api_stream(
            base_url=AZURE_BASE_URL,
            api_key=azure_api_key,
            deployment=AZURE_DEPLOYMENT,
            api_version=AZURE_API_VERSION,
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk
        return
    if use_provider == "doubao":
        if not doubao_api_key:
            yield {"error": "缺少 DOUBAO_API_KEY"}
            return
        async for chunk in _call_openai_compatible_api_stream(
            base_url=DOUBAO_BASE_URL,
            api_key=doubao_api_key,
            model=DOUBAO_MODEL,
            prompt=prompt,
            system_prompt=system_prompt,
        ):
            yield chunk
        return
    # 默认DeepSeek
    if not ds_api_key:
        yield {"error": "缺少 DEEPSEEK_API_KEY"}
        return
    async for chunk in _call_openai_compatible_api_stream(
        base_url=DEEPSEEK_BASE_URL,
        api_key=ds_api_key,
        model=DEEPSEEK_MODEL,
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=8192
    ):
        yield chunk


async def call_vision_api(image_base64: str, prompt: str, provider: str | None = None):
    """
    调用视觉大模型识别图片内容

    Args:
        image_base64: base64编码的图片数据
        prompt: 识别提示词
        provider: "doubao" | "aliyun" | "azure" | "microsoft" | "deepseek"，默认使用豆包

    Returns:
        dict: API返回结果
    """
    use_provider = (provider or "doubao").lower()

    if use_provider == "doubao":
        if not doubao_api_key:
            return {"error": "缺少 DOUBAO_API_KEY"}
        return await _call_doubao_vision_api(image_base64, prompt)

    if use_provider == "aliyun":
        if not aliyun_api_key:
            return {"error": "缺少 ALIYUN_API_KEY"}
        return await _call_aliyun_vision_api(image_base64, prompt)

    if use_provider in ("azure", "microsoft"):
        if not azure_api_key:
            return {"error": "缺少 AZURE_API_KEY"}
        return await _call_azure_vision_api(image_base64, prompt)

    if use_provider == "deepseek":
        if not ds_api_key:
            return {"error": "缺少 DEEPSEEK_API_KEY"}
        return await _call_deepseek_vision_api(image_base64, prompt)

    return {"error": f"不支持的视觉模型provider: {use_provider}"}


async def _call_aliyun_vision_api(image_base64: str, prompt: str):
    """调用阿里云通义千问视觉模型"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {aliyun_api_key}"
    }
    payload = {
        "model": "qwen-vl-plus",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = ALIYUN_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_azure_vision_api(image_base64: str, prompt: str):
    """调用Azure GPT-4o视觉模型"""
    if not AZURE_BASE_URL or not AZURE_DEPLOYMENT:
        return {"error": "缺少 AZURE_BASE_URL 或 AZURE_DEPLOYMENT"}
    headers = {
        "Content-Type": "application/json",
        "api-key": azure_api_key,
    }
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = f"{AZURE_BASE_URL.rstrip('/')}/openai/deployments/{AZURE_DEPLOYMENT}/chat/completions?api-version={AZURE_API_VERSION}"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_doubao_vision_api(image_base64: str, prompt: str):
    """调用字节跳动豆包视觉模型"""
    if not doubao_api_key:
        return {"error": "缺少 DOUBAO_API_KEY"}

    # 豆包视觉模型名称
    vision_model = os.getenv("DOUBAO_VISION_MODEL", "doubao-1-5-vision-pro-32k-250115")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {doubao_api_key}"
    }
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = DOUBAO_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}


async def _call_deepseek_vision_api(image_base64: str, prompt: str):
    """调用DeepSeek视觉模型"""
    if not ds_api_key:
        return {"error": "缺少 DEEPSEEK_API_KEY"}

    # DeepSeek视觉模型名称
    vision_model = os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-chat")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ds_api_key}"
    }
    payload = {
        "model": vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }
    url = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        timeout = aiohttp.ClientTimeout(total=AI_API_TIMEOUT)
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))) as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                error_text = await response.text()
                return {"error": f"API调用失败: {response.status}", "details": error_text}
    except Exception as e:
        return {"error": f"API请求异常: {str(e)}"}
