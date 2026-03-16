import os
import subprocess
import tempfile
import requests
import logging

logger = logging.getLogger(__name__)


def download_and_extract_audio(video_url: str) -> str:
    """
    下载视频并用 ffmpeg 提取音频
    Returns: 本地音频文件路径（mp3）
    """
    tmp_dir = tempfile.mkdtemp(prefix="asr_")
    video_path = os.path.join(tmp_dir, "video.mp4")
    audio_path = os.path.join(tmp_dir, "audio.mp3")

    logger.info(f"[audio_extractor] 临时目录: {tmp_dir}")
    logger.info(f"[audio_extractor] 开始下载视频: {video_url[:80]}...")

    # ── 下载视频 ──────────────────────────────────────
    try:
        resp = requests.get(
            video_url, stream=True, timeout=60,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()

        downloaded = 0
        with open(video_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)

        logger.info(f"[audio_extractor] ✅ 视频下载完成: {video_path}, 大小={downloaded} bytes ({downloaded//1024} KB)")

    except requests.RequestException as e:
        raise Exception(f"下载视频失败: {e}")

    # 检查视频文件
    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        raise Exception(f"视频文件下载后不存在或大小为0: {video_path}")

    # ── ffmpeg 提取音频 ───────────────────────────────
    logger.info(f"[audio_extractor] 开始 ffmpeg 提取音频...")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "mp3",
        "-ar", "16000",   # 16kHz，ASR 推荐采样率
        "-ac", "1",       # 单声道
        "-b:a", "64k",    # 低码率，减小文件体积
        audio_path,
    ]

    logger.info(f"[audio_extractor] ffmpeg 命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"[audio_extractor] ffmpeg stderr:\n{result.stderr[-1000:]}")
        raise Exception(f"ffmpeg 提取音频失败 (returncode={result.returncode}): {result.stderr[-500:]}")

    if not os.path.exists(audio_path):
        raise Exception(f"ffmpeg 执行成功但音频文件未生成: {audio_path}")

    audio_size = os.path.getsize(audio_path)
    if audio_size == 0:
        raise Exception("ffmpeg 生成的音频文件大小为 0")

    logger.info(f"[audio_extractor] ✅ 音频提取成功: {audio_path}, 大小={audio_size} bytes ({audio_size//1024} KB)")

    return audio_path
