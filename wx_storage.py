"""
微信云托管 - 云存储上传模块
==============================
上传流程（两步）：
  Step 1: POST http://api.weixin.qq.com/tcb/uploadfile
          → 获取 url / authorization / token / file_id
  Step 2: PUT {url}  (multipart/form-data 或 直接 PUT body)
          → 实际把文件上传到 COS

注意：需要在微信云托管控制台开启"开放接口服务"，
      容器内调用无需 access_token，传 env 即可。
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# 云托管会自动注入 CBR_ENV_ID 环境变量
WX_ENV_ID = os.environ.get("CBR_ENV_ID", os.environ.get("WX_ENV_ID", ""))
# 微信内网 API（云托管容器内专用）
WX_API_BASE = "http://api.weixin.qq.com"


def upload_to_wx_storage(local_file_path: str, cloud_path: str) -> str:
    """
    上传本地文件到微信云存储，返回可供 ASR 访问的下载 URL

    Args:
        local_file_path: 本地文件绝对路径
        cloud_path: 云端路径，如 "asr_audio/xxx.mp3"（不要以 / 开头）

    Returns:
        str: 文件的 COS 公网访问 URL
    """
    # ---------- 前置检查 ----------
    if not WX_ENV_ID:
        raise Exception(
            "缺少环境变量 CBR_ENV_ID，请确认已在微信云托管控制台开启「开放接口服务」，"
            "或手动设置 WX_ENV_ID 环境变量"
        )

    if not os.path.exists(local_file_path):
        raise Exception(f"本地文件不存在: {local_file_path}")

    file_size = os.path.getsize(local_file_path)
    logger.info(f"[wx_storage] 准备上传: {local_file_path} ({file_size} bytes) → {cloud_path}")

    # ---------- Step 1: 获取上传凭证 ----------
    logger.info(f"[wx_storage] Step1: 请求上传凭证, env={WX_ENV_ID}, path={cloud_path}")
    try:
        resp1 = requests.post(
            f"{WX_API_BASE}/tcb/uploadfile",
            json={"env": WX_ENV_ID, "path": cloud_path},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise Exception(f"[wx_storage] Step1 请求失败（网络/连接错误）: {e}")

    logger.info(f"[wx_storage] Step1 HTTP状态: {resp1.status_code}")
    logger.info(f"[wx_storage] Step1 响应体: {resp1.text[:500]}")

    if resp1.status_code != 200:
        raise Exception(
            f"[wx_storage] Step1 HTTP错误 {resp1.status_code}: {resp1.text[:300]}"
        )

    cred = resp1.json()
    if cred.get("errcode", 0) != 0:
        raise Exception(
            f"[wx_storage] Step1 微信返回错误 errcode={cred.get('errcode')}, "
            f"errmsg={cred.get('errmsg')}"
        )

    upload_url   = cred["url"]
    token        = cred["token"]
    authorization = cred["authorization"]
    cos_file_id  = cred.get("cos_file_id", "")
    file_id      = cred["file_id"]      # cloud://... 格式的 fileID

    logger.info(f"[wx_storage] Step1 成功, upload_url={upload_url}, file_id={file_id}")

    # ---------- Step 2: 上传文件到 COS ----------
    logger.info(f"[wx_storage] Step2: 开始 PUT 上传文件到 COS")
    try:
        with open(local_file_path, "rb") as f:
            file_content = f.read()

        # 微信云存储上传：multipart/form-data，字段顺序固定
        files = {
            "key":           (None, cloud_path),
            "Signature":     (None, authorization),
            "x-cos-security-token": (None, token),
            "x-cos-meta-fileid": (None, cos_file_id),
            "file":          (os.path.basename(local_file_path), file_content, "audio/mpeg"),
        }

        resp2 = requests.post(
            upload_url,
            files=files,
            timeout=120,
        )
    except requests.RequestException as e:
        raise Exception(f"[wx_storage] Step2 上传到COS失败（网络错误）: {e}")

    logger.info(f"[wx_storage] Step2 HTTP状态: {resp2.status_code}")
    if resp2.status_code not in (200, 204):
        logger.error(f"[wx_storage] Step2 响应体: {resp2.text[:500]}")
        raise Exception(
            f"[wx_storage] Step2 COS上传失败 HTTP {resp2.status_code}: {resp2.text[:300]}"
        )

    # ---------- 获取下载 URL ----------
    logger.info(f"[wx_storage] Step3: 获取文件下载URL, file_id={file_id}")
    try:
        resp3 = requests.post(
            f"{WX_API_BASE}/tcb/batchdownloadfile",
            json={
                "env": WX_ENV_ID,
                "file_list": [{"fileid": file_id, "max_age": 7200}],
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise Exception(f"[wx_storage] Step3 获取下载URL失败: {e}")

    logger.info(f"[wx_storage] Step3 HTTP状态: {resp3.status_code}")
    logger.info(f"[wx_storage] Step3 响应体: {resp3.text[:500]}")

    if resp3.status_code != 200:
        raise Exception(f"[wx_storage] Step3 HTTP错误: {resp3.status_code}")

    dl_data = resp3.json()
    if dl_data.get("errcode", 0) != 0:
        raise Exception(
            f"[wx_storage] Step3 微信返回错误 errcode={dl_data.get('errcode')}, "
            f"errmsg={dl_data.get('errmsg')}"
        )

    file_list = dl_data.get("file_list", [])
    if not file_list:
        raise Exception("[wx_storage] Step3 返回 file_list 为空")

    download_url = file_list[0].get("download_url", "")
    if not download_url:
        raise Exception(f"[wx_storage] Step3 download_url 为空，响应: {dl_data}")

    logger.info(f"[wx_storage] 全部完成！download_url={download_url[:80]}...")
    return download_url
