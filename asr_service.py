import os
import json
import time
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.asr.v20190614 import asr_client, models


class TencentASRService:
    """腾讯云语音识别服务（录音文件识别，支持超过60秒音频）"""

    def __init__(self):
        secret_id = os.environ.get("TENCENT_CLOUD_SECRET_ID")
        secret_key = os.environ.get("TENCENT_CLOUD_SECRET_KEY")
        if not all([secret_id, secret_key]):
            raise ValueError("请配置 TENCENT_CLOUD_SECRET_ID 和 TENCENT_CLOUD_SECRET_KEY")

        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        self.client = asr_client.AsrClient(cred, "", client_profile)

    def submit_task(self, audio_url: str, engine_type: str = "16k_zh") -> int:
        """
        提交录音文件识别任务（异步）
        Returns: TaskId
        """
        try:
            req = models.CreateRecTaskRequest()
            params = {
                "EngineModelType": engine_type,
                "ChannelNum": 1,
                "ResTextFormat": 0,
                "SourceType": 0,  # URL 模式
                "Url": audio_url,
            }
            req.from_json_string(json.dumps(params))
            resp = self.client.CreateRecTask(req)
            result = json.loads(resp.to_json_string())
            return result["Data"]["TaskId"]
        except TencentCloudSDKException as e:
            raise Exception(f"提交识别任务失败: {e.message}")

    def query_task(self, task_id: int) -> dict:
        """
        查询识别任务状态
        Returns: {"status": "processing"|"success"|"failed", "text": "..."}
        """
        try:
            req = models.DescribeTaskStatusRequest()
            req.from_json_string(json.dumps({"TaskId": task_id}))
            resp = self.client.DescribeTaskStatus(req)
            result = json.loads(resp.to_json_string())
            data = result["Data"]

            # status: 0=等待 1=执行中 2=成功 3=失败
            status_code = data.get("Status")
            if status_code in (0, 1):
                return {"status": "processing"}
            elif status_code == 2:
                return {"status": "success", "text": data.get("Result", "")}
            else:
                return {"status": "failed", "error": data.get("ErrorMsg", "识别失败")}
        except TencentCloudSDKException as e:
            raise Exception(f"查询任务失败: {e.message}")


_asr_service = None


def get_asr_service() -> TencentASRService:
    global _asr_service
    if _asr_service is None:
        _asr_service = TencentASRService()
    return _asr_service
