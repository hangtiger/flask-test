import requests
import os


SHANHAI_API_URL = "https://apione.apibyte.cn/douyinparse"
SHANHAI_API_KEY = os.environ.get("SHANHAI_API_KEY", "")


def parse_douyin_url(share_url: str) -> dict:
    """
    调用山海云端 API 解析抖音分享链接
    返回包含 720p 视频直链的字典
    """
    params = {"url": share_url}
    if SHANHAI_API_KEY:
        params["key"] = SHANHAI_API_KEY

    try:
        resp = requests.get(SHANHAI_API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise Exception(f"解析接口请求失败: {e}")

    if data.get("code") != 200:
        raise Exception(f"解析失败: {data.get('msg', '未知错误')}")

    video_info = data.get("data", {}).get("video", {})

    # 优先取 720p，没有则取 play_url
    video_url = (
        video_info.get("720p")
        or video_info.get("play_url")
    )

    if not video_url:
        raise Exception("未能获取到视频链接")

    return {
        "video_url": video_url,
        "title": data["data"].get("title", ""),
    }
