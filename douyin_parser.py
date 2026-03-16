import requests
import os
import logging

logger = logging.getLogger(__name__)

SHANHAI_API_URL = "https://apione.apibyte.cn/douyinparse"
SHANHAI_API_KEY = os.environ.get("SHANHAI_API_KEY", "")


def parse_douyin_url(share_url: str) -> dict:
    """
    调用山海云端 API 解析抖音分享链接，返回 720p 视频直链
    """
    params = {"url": share_url}
    if SHANHAI_API_KEY:
        params["key"] = SHANHAI_API_KEY

    logger.info(f"[douyin_parser] 请求山海云端解析: {share_url[:60]}")

    try:
        resp = requests.get(SHANHAI_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise Exception(f"解析接口请求失败: {e}")

    logger.info(f"[douyin_parser] 响应: code={data.get('code')}, msg={data.get('msg')}")

    if data.get("code") != 200:
        raise Exception(f"解析失败: {data.get('msg', '未知错误')}")

    video_info = data.get("data", {}).get("video", {})
    video_url = video_info.get("720p") or video_info.get("play_url")

    if not video_url:
        raise Exception("未能获取到视频链接")

    title = data["data"].get("title", "")
    logger.info(f"[douyin_parser] ✅ 解析成功, title={title!r}, url={video_url[:80]}")

    return {"video_url": video_url, "title": title}
