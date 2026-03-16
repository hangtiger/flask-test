import os
from qcloud_cos import CosConfig, CosS3Client

BUCKET = os.environ.get("COS_BUCKET", "")
REGION = os.environ.get("COS_REGION", "ap-shanghai")
SECRET_ID = os.environ.get("TENCENT_CLOUD_SECRET_ID", "")
SECRET_KEY = os.environ.get("TENCENT_CLOUD_SECRET_KEY", "")


def upload_to_wx_storage(local_file_path: str, cloud_path: str) -> str:
    """
    上传本地音频文件到 COS，返回公网访问 URL

    Args:
        local_file_path: 本地文件路径
        cloud_path: 对象路径，如 "asr_audio/xxx.mp3"

    Returns:
        str: 公网访问 URL
    """
    if not all([BUCKET, SECRET_ID, SECRET_KEY]):
        raise Exception("缺少 COS 配置，请检查环境变量 COS_BUCKET / TENCENT_CLOUD_SECRET_ID / TENCENT_CLOUD_SECRET_KEY")

    config = CosConfig(Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY)
    client = CosS3Client(config)

    with open(local_file_path, "rb") as f:
        client.put_object(
            Bucket=BUCKET,
            Body=f,
            Key=cloud_path,
            ContentType="audio/mpeg",
        )

    return f"https://{BUCKET}.cos.{REGION}.myqcloud.com/{cloud_path}"
