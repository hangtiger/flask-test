import os
import json
import requests

ENV_ID = os.environ.get("ENV_ID", "")

# 云托管内网调用微信云存储接口（无需 access_token，自动鉴权）
_BASE = "http://api.weixin.qq.com"


def upload_to_wx_storage(local_file_path: str, cloud_path: str) -> str:
    """
    通过云托管内网接口上传文件到微信云存储，返回公网临时下载 URL（2小时有效）

    Args:
        local_file_path: 本地文件路径
        cloud_path: 云存储路径，如 "asr_audio/xxx.mp3"

    Returns:
        str: 临时下载 URL
    """
    if not ENV_ID:
        raise Exception("未配置 ENV_ID 环境变量")

    # 第一步：获取上传凭证
    resp = requests.post(
        f"{_BASE}/tcb/uploadfile",
        json={"env": ENV_ID, "path": cloud_path},
        timeout=10,
    )
    resp.raise_for_status()
    info = resp.json()
    if info.get("errcode", 0) != 0:
        raise Exception(f"获取上传凭证失败: {info.get('errmsg')}")

    # 第二步：上传到 COS
    with open(local_file_path, "rb") as f:
        file_data = f.read()

    form = {
        "key": cloud_path,
        "Signature": info["authorization"],
        "x-cos-security-token": info["token"],
        "x-cos-meta-fileid": info["cos_file_id"],
    }
    files = {"file": (os.path.basename(local_file_path), file_data, "audio/mpeg")}
    cos_resp = requests.post(info["url"], data=form, files=files, timeout=60)
    cos_resp.raise_for_status()

    file_id = info["file_id"]

    # 第三步：换取临时下载 URL
    dl_resp = requests.post(
        f"{_BASE}/tcb/batchdownloadfile",
        json={"env": ENV_ID, "file_list": [{"fileid": file_id, "max_age": 7200}]},
        timeout=10,
    )
    dl_resp.raise_for_status()
    dl_info = dl_resp.json()
    if dl_info.get("errcode", 0) != 0:
        raise Exception(f"获取下载链接失败: {dl_info.get('errmsg')}")

    return dl_info["file_list"][0]["download_url"]
