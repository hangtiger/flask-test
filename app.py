from flask import Flask, request, jsonify
import os
import time
import traceback
import threading
import logging
import sys

# ─── 日志配置：输出到 stdout，云托管可在日志中心查看 ───────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("app")

from douyin_parser import parse_douyin_url
from audio_extractor import download_and_extract_audio
from wx_storage import upload_to_wx_storage
from asr_service import get_asr_service

app = Flask(__name__)

# 内存任务表：{task_id: {"status": ..., "text": ..., "error": ..., "debug": [...]}}
_tasks: dict = {}
_tasks_lock = threading.Lock()


def _add_debug(task_id: str, msg: str):
    """追加一条调试信息到任务的 debug 列表"""
    logger.info(f"[task={task_id}] {msg}")
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].setdefault("debug", []).append(
                f"[{time.strftime('%H:%M:%S')}] {msg}"
            )


def _process_task(task_id: str, share_url: str):
    """后台线程：解析 → 下载 → 提取音频 → 上传云存储 → 提交 ASR → 轮询结果"""

    def update(status, **kwargs):
        with _tasks_lock:
            _tasks[task_id].update({"status": status, **kwargs})

    audio_path = None
    try:
        # ──────────────────────────────────────────────
        # Step 1: 解析抖音链接
        # ──────────────────────────────────────────────
        update("parsing")
        _add_debug(task_id, f"Step1 开始解析抖音链接: {share_url[:60]}...")

        parsed = parse_douyin_url(share_url)
        video_url = parsed["video_url"]
        title = parsed.get("title", "")

        _add_debug(task_id, f"Step1 ✅ 解析成功, title={title!r}, video_url={video_url[:80]}...")

        # ──────────────────────────────────────────────
        # Step 2: 下载视频并提取音频
        # ──────────────────────────────────────────────
        update("downloading")
        _add_debug(task_id, "Step2 开始下载视频并用 ffmpeg 提取音频...")

        audio_path = download_and_extract_audio(video_url)

        # 检查音频文件
        if not os.path.exists(audio_path):
            raise Exception(f"Step2 ❌ 音频文件未生成: {audio_path}")

        audio_size = os.path.getsize(audio_path)
        _add_debug(task_id, f"Step2 ✅ 音频提取成功: {audio_path}, 大小={audio_size} bytes ({audio_size//1024} KB)")

        if audio_size == 0:
            raise Exception("Step2 ❌ 音频文件大小为 0，ffmpeg 提取失败")

        # ──────────────────────────────────────────────
        # Step 3: 上传到微信云存储
        # ──────────────────────────────────────────────
        update("uploading")
        cloud_path = f"asr_audio/{task_id}.mp3"
        _add_debug(task_id, f"Step3 开始上传音频到云存储: cloud_path={cloud_path}")

        download_url = upload_to_wx_storage(audio_path, cloud_path)

        _add_debug(task_id, f"Step3 ✅ 上传成功, download_url={download_url[:80]}...")

        # ──────────────────────────────────────────────
        # Step 4: 提交腾讯云 ASR 任务
        # ──────────────────────────────────────────────
        update("recognizing")
        _add_debug(task_id, "Step4 开始提交 ASR 识别任务...")

        asr = get_asr_service()
        asr_task_id = asr.submit_task(download_url)

        _add_debug(task_id, f"Step4 ✅ ASR 任务提交成功, asr_task_id={asr_task_id}")

        # ──────────────────────────────────────────────
        # Step 5: 轮询 ASR 结果（最多等 5 分钟）
        # ──────────────────────────────────────────────
        _add_debug(task_id, "Step5 开始轮询 ASR 结果（每5秒一次，最多60次）...")

        for i in range(60):
            time.sleep(5)
            result = asr.query_task(asr_task_id)
            _add_debug(task_id, f"Step5 第{i+1}次轮询: status={result['status']}")

            if result["status"] == "success":
                text = result["text"]
                _add_debug(task_id, f"Step5 ✅ 识别完成! 文字长度={len(text)} 字符")
                update("done", text=text)
                return
            elif result["status"] == "failed":
                err = result.get("error", "ASR 识别失败")
                _add_debug(task_id, f"Step5 ❌ ASR 识别失败: {err}")
                update("failed", error=err)
                return

        _add_debug(task_id, "Step5 ❌ 识别超时（5分钟）")
        update("failed", error="识别超时，请重试")

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[task={task_id}] 任务异常:\n{tb}")
        _add_debug(task_id, f"❌ 异常: {str(e)}")
        update("failed", error=str(e))

    finally:
        # 清理本地临时文件
        if audio_path and os.path.exists(audio_path):
            try:
                import shutil
                tmp_dir = os.path.dirname(audio_path)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                _add_debug(task_id, f"临时文件已清理: {tmp_dir}")
            except Exception:
                pass


@app.route("/api/submit", methods=["POST"])
def submit():
    """提交抖音链接转文字任务，立即返回 taskId"""
    data = request.get_json()
    logger.info(f"/api/submit 收到请求: {data}")

    if not data or not data.get("url"):
        return jsonify({"success": False, "error": "缺少 url 参数"}), 400

    share_url = data["url"].strip()
    task_id = f"task_{int(time.time() * 1000)}"

    logger.info(f"创建任务 task_id={task_id}, url={share_url[:60]}")

    with _tasks_lock:
        _tasks[task_id] = {"status": "pending", "debug": []}

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

    status_msg = {
        "pending":     "等待处理...",
        "parsing":     "正在解析视频链接...",
        "downloading": "正在下载视频并提取音频...",
        "uploading":   "正在上传音频到云存储...",
        "recognizing": "正在识别语音...",
        "done":        "识别完成",
        "failed":      "识别失败",
    }

    resp = {
        "success":   True,
        "status":    status,
        "statusMsg": status_msg.get(status, status),
        "debug":     task.get("debug", []),   # ← 调试信息，前端可展示
    }

    if status == "done":
        resp["text"] = task.get("text", "")
    elif status == "failed":
        resp["error"] = task.get("error", "未知错误")

    return jsonify(resp)


@app.route("/api/debug/<task_id>", methods=["GET"])
def get_debug(task_id):
    """专用调试接口：返回任务完整信息（含 debug 日志）"""
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    return jsonify({
        "success": True,
        "task_id": task_id,
        "status":  task.get("status"),
        "error":   task.get("error"),
        "text_len": len(task.get("text", "")),
        "debug":   task.get("debug", []),
    })


@app.route("/api/health", methods=["GET"])
def health():
    env_check = {
        "CBR_ENV_ID":               bool(os.environ.get("CBR_ENV_ID")),
        "TENCENT_CLOUD_SECRET_ID":  bool(os.environ.get("TENCENT_CLOUD_SECRET_ID")),
        "TENCENT_CLOUD_SECRET_KEY": bool(os.environ.get("TENCENT_CLOUD_SECRET_KEY")),
        "SHANHAI_API_KEY":          bool(os.environ.get("SHANHAI_API_KEY")),
    }
    logger.info(f"/api/health 环境变量检查: {env_check}")
    return jsonify({
        "status":    "healthy",
        "service":   "douyin-to-text",
        "env_check": env_check,
    })


@app.route("/")
def index():
    return "<h1>抖音视频转文字服务</h1><p>接口：POST /api/submit，GET /api/result/&lt;task_id&gt;</p>"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    logger.info(f"服务启动, port={port}")
    app.run(debug=False, host="0.0.0.0", port=port)
