from flask import Flask, request, jsonify
import os
import time
import traceback
import threading

from douyin_parser import parse_douyin_url
from audio_extractor import download_and_extract_audio
from wx_storage import upload_to_wx_storage
from asr_service import get_asr_service

app = Flask(__name__)

# 内存任务表：{task_id: {"status": ..., "text": ..., "error": ...}}
# 云托管单实例足够用于测试，生产环境建议换 Redis
_tasks: dict = {}
_tasks_lock = threading.Lock()


def _process_task(task_id: str, share_url: str):
    """后台线程：解析 → 下载 → 提取音频 → 上传云存储 → 提交 ASR"""
    def update(status, **kwargs):
        with _tasks_lock:
            _tasks[task_id].update({"status": status, **kwargs})

    audio_path = None
    try:
        update("parsing")

        # 1. 解析抖音链接
        parsed = parse_douyin_url(share_url)
        video_url = parsed["video_url"]
        update("downloading")

        # 2. 下载视频并提取音频
        audio_path = download_and_extract_audio(video_url)
        update("uploading")

        # 3. 上传到微信云存储
        cloud_path = f"asr_audio/{task_id}.mp3"
        download_url = upload_to_wx_storage(audio_path, cloud_path)
        update("recognizing")

        # 4. 提交腾讯云 ASR 任务
        asr = get_asr_service()
        asr_task_id = asr.submit_task(download_url)

        # 5. 轮询 ASR 结果（最多等 5 分钟）
        for _ in range(60):
            time.sleep(5)
            result = asr.query_task(asr_task_id)
            if result["status"] == "success":
                update("done", text=result["text"])
                return
            elif result["status"] == "failed":
                update("failed", error=result.get("error", "ASR 识别失败"))
                return

        update("failed", error="识别超时，请重试")

    except Exception as e:
        traceback.print_exc()
        update("failed", error=str(e))
    finally:
        # 清理本地临时文件
        if audio_path and os.path.exists(audio_path):
            try:
                import shutil
                shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)
            except Exception:
                pass


@app.route("/api/submit", methods=["POST"])
def submit():
    """提交抖音链接转文字任务，立即返回 taskId"""
    data = request.get_json()
    if not data or not data.get("url"):
        return jsonify({"success": False, "error": "缺少 url 参数"}), 400

    share_url = data["url"].strip()
    task_id = f"task_{int(time.time() * 1000)}"

    with _tasks_lock:
        _tasks[task_id] = {"status": "pending"}

    thread = threading.Thread(target=_process_task, args=(task_id, share_url), daemon=True)
    thread.start()

    return jsonify({"success": True, "taskId": task_id})


@app.route("/api/result/<task_id>", methods=["GET"])
def get_result(task_id):
    """查询任务结果"""
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    status = task["status"]

    # 状态说明映射（给前端展示用）
    status_msg = {
        "pending": "等待处理...",
        "parsing": "正在解析视频链接...",
        "downloading": "正在下载视频...",
        "uploading": "正在处理音频...",
        "recognizing": "正在识别语音...",
        "done": "识别完成",
        "failed": "识别失败",
    }

    resp = {
        "success": True,
        "status": status,
        "statusMsg": status_msg.get(status, status),
    }

    if status == "done":
        resp["text"] = task.get("text", "")
    elif status == "failed":
        resp["error"] = task.get("error", "未知错误")

    return jsonify(resp)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "douyin-to-text"})


@app.route("/")
def index():
    return "<h1>抖音视频转文字服务</h1>"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(debug=False, host="0.0.0.0", port=port)
