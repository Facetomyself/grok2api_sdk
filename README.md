# grok2api Python SDK 模板

这是一个可直接复用的模块化 SDK 模板，默认建议通过环境变量或 `.env` 注入配置：

- `base_url`: `http://your-host:8000`
- `api_key`: `sk-your_api_key_here`

> 建议不要在代码或文档中写明文密钥。

## 这版新增了啥

- 图片接口完整适配：`GET /v1/images/method`、`POST /v1/images/generations`、`POST /v1/images/edits`（`multipart/form-data`）。
- 视频接口完整适配：按 `grok2api` 源码约定，走 `POST /v1/chat/completions` + `model=grok-imagine-1.0-video` + `video_config`。
- 同步/异步双栈都支持图片和视频。
- `multipart` 请求同样走重试策略和请求 hook，不是“只给 JSON 开绿灯”。
- 支持本地图片上传编辑（`images=[Path(...)]` / `bytes`）。
- 支持将图片和视频一键下载到本地目录（`images.download_all`、`videos.download_assets`）。

## 目录结构

```text
grok_sdk/
  __init__.py
  client.py
  async_client.py
  config.py
  exceptions.py
  hooks.py
  transport.py
  resources/
    __init__.py
    chat.py
    images.py
    models.py
    videos.py
    async_chat.py
    async_images.py
    async_models.py
    async_videos.py
    media_utils.py
examples/
  basic_chat.py
  stream_chat.py
  async_chat.py
  retry_with_hook.py
  image_generate.py
  image_edit.py
  video_generate.py
  async_video_generate.py
```

## 安装

```bash
pip install -e .
```

## 本地配置（推荐）

项目根目录创建 `.env`（SDK 会自动读取；也支持用 `GROK_DOTENV=/path/to/.env` 指定位置）：

```bash
GROK_BASE_URL=http://your-host:8000
GROK_API_KEY=sk-your_api_key_here
# 如果 GROK_API_KEY 为空，SDK 不会发送 Authorization 头（避免 Authorization: Bearer  导致上游鉴权误判）
GROK_TIMEOUT=30
GROK_VERIFY_SSL=true
GROK_MAX_RETRIES=2
GROK_RETRY_BACKOFF_BASE=0.5
GROK_RETRY_BACKOFF_MAX=8
```

仓库已通过 `.gitignore` 忽略 `.env`，避免误提交敏感信息。

## 快速开始（文本）

## OpenAI Responses API 兼容接口（grok2api /v1/responses）

```python
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    resp = client.responses.create(
        model="grok-4",
        input="解释一下量子隧穿",
        stream=False,
    )
    print(resp)
```

```python
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    resp = client.chat.completions.create(
        model="grok-3",
        messages=[{"role": "user", "content": "你好"}],
    )
    print(resp)
```

## 图片生成

```python
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    print(client.images.method())
    result = client.images.generate(
        model="grok-imagine-1.0",
        prompt="A cyberpunk city at sunrise",
        n=1,
        response_format="url",
    )
    print(result)
    saved_files = client.images.download_all(result, "outputs/images")
    print(saved_files)
```

## 图片编辑（multipart/form-data）

```python
from pathlib import Path
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    result = client.images.edit(
        model="grok-imagine-1.0-edit",
        prompt="Make this image watercolor style",
        images=[Path("examples/local_input.png")],  # 本地文件直接上传
        n=1,
        response_format="url",
    )
    print(result)
    saved_files = client.images.download_all(result, "outputs/edited_images")
    print(saved_files)
```

说明：`/v1/images/edits` 依赖上游账号能力与上传校验，若账号或资源不满足条件，可能返回上游错误。

## 视频生成（重点）

### OpenAI videos.create 兼容接口（grok2api /v1/videos）

```python
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    resp = client.openai_videos.create(
        model="grok-imagine-1.0-video",
        prompt="霓虹雨夜街头，慢镜头追拍",
        size="1792x1024",
        seconds=18,
        quality="standard",
    )
    print(resp)
```

---

`grok2api` 也支持通过 `/v1/chat/completions` + `video_config` 调用视频能力：

- 路径：`POST /v1/chat/completions`
- 模型：`grok-imagine-1.0-video`
- 参数：`video_config = {aspect_ratio, video_length, resolution, preset}`

```python
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    result = client.videos.generate(
        model="grok-imagine-1.0-video",
        prompt="A small robot dancing in neon rain",
        request_timeout=180,
        video_length=5,
        aspect_ratio="3:2",
        resolution="SD",
        preset="normal",
    )
    print(result)
    print(client.videos.extract_assets(result))
    saved = client.videos.download_assets(result, "outputs/videos")
    print(saved)
```

`extract_assets` 会从响应里解析出：

- `videos`: 视频链接（如 `.mp4`）
- `posters`: 预览图链接

说明：视频生成耗时通常高于文本接口，建议把 `request_timeout` 设为 `120` 秒以上。

## 本地下载辅助方法

- `client.images.extract_urls(response)`：提取图片 URL 列表
- `client.images.download(url, destination, skip_if_exists=False, resume=False)`：下载单张图片
- `client.images.download_all(response, output_dir, skip_if_exists=False, resume=False)`：批量下载图片结果
- `client.videos.extract_assets(response)`：提取视频和海报 URL
- `client.videos.download(url, destination, skip_if_exists=False, resume=False)`：下载单个媒体文件
- `client.videos.download_assets(response, output_dir, skip_if_exists=False, resume=False)`：批量下载视频与海报

参数说明：

- `skip_if_exists=True`：目标文件已存在时直接跳过下载
- `resume=True`：尝试断点续传（服务端不支持 Range 时会自动回退为完整下载）

示例（断点续传 + 已存在跳过）：

```python
from pathlib import Path
from grok_sdk import GrokSDKClient

with GrokSDKClient() as client:
    result = client.images.generate(
        model="grok-imagine-1.0",
        prompt="A clean product photo",
        n=1,
        response_format="url",
    )

    # 第一次下载
    saved = client.images.download_all(result, Path("outputs") / "images")

    # 重复执行任务时：已有文件直接跳过；如果文件不完整则尝试续传
    saved_again = client.images.download_all(
        result,
        Path("outputs") / "images",
        skip_if_exists=True,
        resume=True,
    )
    print(saved, saved_again)
```

异步客户端提供同名能力：

- `await client.images.download(...)`
- `await client.images.download_all(...)`
- `await client.videos.download(...)`
- `await client.videos.download_assets(...)`

## 异步调用（Async）

```python
import asyncio
from grok_sdk import AsyncGrokSDKClient


async def main() -> None:
    async with AsyncGrokSDKClient() as client:
        result = await client.images.generate(
            model="grok-imagine-1.0",
            prompt="A panda in a library",
            n=1,
            response_format="url",
        )
        print(result)


asyncio.run(main())
```

## 自动重试与退避

默认重试策略：

- `max_retries=2`（总尝试次数 = 3）
- 重试状态码：`408`、`425`、`429` 和 `5xx`
- 指数退避：`retry_backoff_base * 2^(attempt-1)`，默认上限 `8` 秒
- 如果服务返回 `Retry-After`，优先使用该值（受最大退避上限约束）

## 请求日志钩子（Hook）

```python
from grok_sdk import GrokSDKClient, RequestLogEvent


def log_hook(event: RequestLogEvent) -> None:
    print(
        f"[{event.transport}] {event.phase} {event.method} {event.path} "
        f"attempt={event.attempt}/{event.max_attempts} "
        f"status={event.status_code} retry_delay={event.retry_delay_s} "
        f"cost_ms={event.duration_ms}"
    )


with GrokSDKClient(request_log_hook=log_hook) as client:
    print(client.models.list())
```

## 环境变量覆盖（推荐）

Windows:

```bash
set GROK_BASE_URL=http://your-host:8000
set GROK_API_KEY=sk-your_api_key_here
set GROK_TIMEOUT=30
set GROK_VERIFY_SSL=true
set GROK_MAX_RETRIES=2
set GROK_RETRY_BACKOFF_BASE=0.5
set GROK_RETRY_BACKOFF_MAX=8
```

Linux/macOS:

```bash
export GROK_BASE_URL=http://your-host:8000
export GROK_API_KEY=sk-your_api_key_here
export GROK_TIMEOUT=30
export GROK_VERIFY_SSL=true
export GROK_MAX_RETRIES=2
export GROK_RETRY_BACKOFF_BASE=0.5
export GROK_RETRY_BACKOFF_MAX=8
```
