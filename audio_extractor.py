import os
import subprocess
import tempfile
import requests


def download_and_extract_audio(video_url: str) -> str:
    """
    下载视频并用 ffmpeg 提取音频
    Returns: 本地音频文件路径（mp3）
    """
    tmp_dir = tempfile.mkdtemp(prefix="asr_")
    video_path = os.path.join(tmp_dir, "video.mp4")
    audio_path = os.path.join(tmp_dir, "audio.mp3")

    # 下载视频
    try:
        resp = requests.get(video_url, stream=True, timeout=60,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        with open(video_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.RequestException as e:
        raise Exception(f"下载视频失败: {e}")

    # ffmpeg 提取音频
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "mp3",
        "-ar", "16000",  # 16kHz，ASR 推荐采样率
        "-ac", "1",      # 单声道
        "-b:a", "64k",   # 低码率，减小文件体积
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"ffmpeg 提取音频失败: {result.stderr[-500:]}")

    if not os.path.exists(audio_path):
        raise Exception("音频文件未生成")

    return audio_path
