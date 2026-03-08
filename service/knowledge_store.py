# service/knowledge_store.py
"""
知识库检索模块 - 阿里云百炼 RAG API 版
无需本地向量库，纯 API 调用

支持两种模式：
  1. dashscope 简单模式：只需 API Key，适合快速检索
  2. 官方 SDK 模式：需 AccessKey，支持完整知识库管理（上传/解析/索引）
"""
import os
import time
import hashlib
from typing import List, Optional, Union, Dict

# ── 依赖导入：优先官方 SDK，备选 dashscope 简单封装 ───────────────────────────
try:
    from alibabacloud_bailian20231229 import models as bailian_models
    from alibabacloud_bailian20231229.client import Client as BailianClient
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_tea_util import models as util_models

    _HAS_OFFICIAL_SDK = True
except ImportError:
    _HAS_OFFICIAL_SDK = False
    import dashscope
    from dashscope import KnowledgeRetrieval

from langchain_core.documents import Document


class KnowledgeStore:
    """基于阿里云百炼的云端知识库检索"""

    def __init__(
            self,
            db=None,  # 兼容原接口，实际不用
            api_key: Optional[str] = None,
            knowledge_base_id: Optional[str] = None,
            workspace_id: Optional[str] = None,
            access_key_id: Optional[str] = None,
            access_key_secret: Optional[str] = None,
    ):
        """
        初始化百炼知识库检索

        Args:
            db: 兼容参数，忽略
            api_key: DashScope API Key（用于简单检索模式）
            knowledge_base_id: 百炼控制台创建的知识库 ID
            workspace_id: 百炼业务空间 ID（用于官方 SDK 模式）
            access_key_id: 阿里云 AccessKey ID（用于官方 SDK 模式）
            access_key_secret: 阿里云 AccessKey Secret（用于官方 SDK 模式）
        """
        # 从参数或环境变量读取配置
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.knowledge_base_id = knowledge_base_id or os.getenv("BAILOU_KNOWLEDGE_BASE_ID")
        self.workspace_id = workspace_id or os.getenv("BAILOU_WORKSPACE_ID")
        self.access_key_id = access_key_id or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        self.access_key_secret = access_key_secret or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")

        # 验证必要配置
        if not self.knowledge_base_id:
            raise ValueError("请设置 BAILOU_KNOWLEDGE_BASE_ID 环境变量（百炼知识库 ID）")

        # 初始化模式判断
        if _HAS_OFFICIAL_SDK and self.access_key_id and self.access_key_secret:
            self._mode = "official_sdk"
            self._init_official_sdk()
        elif self.api_key:
            self._mode = "dashscope"
            dashscope.api_key = self.api_key
        else:
            raise ValueError("请配置 DASHSCOPE_API_KEY 或 ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET")

    def _init_official_sdk(self):
        """初始化官方 SDK 客户端"""
        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            endpoint='bailian.cn-beijing.aliyuncs.com'  # 可按需更换地域
        )
        self._client = BailianClient(config)

    def retrieve(
            self,
            query: str,
            job_position_id: int = 0,  # 兼容参数，百炼侧可在知识库元数据中过滤
            top_k: int = 3,
    ) -> List[str]:
        """
        调用百炼知识库检索接口

        Args:
            query: 用户问题
            job_position_id: 岗位 ID（预留，可在百炼控制台用元数据过滤）
            top_k: 返回结果数量

        Returns:
            相关知识片段列表
        """
        try:
            if self._mode == "official_sdk":
                results = self._retrieve_with_official_sdk(query, top_k)
            else:
                results = self._retrieve_with_dashscope(query, top_k)

            if not results:
                return ["📭 知识库中未找到相关内容。"]

            # 格式化输出
            contents = []
            for i, item in enumerate(results, 1):
                text = item.get("content", "").strip()
                title = item.get("title", "")
                score = item.get("score", 0)
                source = item.get("source", "")

                if text:
                    parts = []
                    if title:
                        parts.append(f"【{title}】")
                    if source:
                        parts.append(f"📄 {source}")
                    parts.append(text)
                    if score:
                        parts.append(f"(相关度: {score:.2f})")
                    contents.append(" ".join(parts))

            return contents

        except Exception as e:
            return [f"⚠️ 检索异常：{str(e)}"]

    def _retrieve_with_dashscope(self, query: str, top_k: int) -> List[dict]:
        """使用 dashscope 简单封装调用"""
        response = KnowledgeRetrieval.call(
            knowledge_base_id=self.knowledge_base_id,
            query=query,
            top_k=top_k,
            rerank=True,
        )

        if response.status_code != 200:
            raise RuntimeError(f"百炼检索失败：{response.message}")

        return response.output.get("results", [])

    def _retrieve_with_official_sdk(self, query: str, top_k: int) -> List[dict]:
        """使用官方 SDK 调用检索接口"""
        # 构造检索请求
        request = bailian_models.RetrieveKnowledgeRequest(
            knowledge_base_id=self.knowledge_base_id,
            query=query,
            top_k=top_k,
            rerank=True,
        )
        runtime = util_models.RuntimeOptions()
        headers = {}

        response = self._client.retrieve_knowledge_with_options(
            self.workspace_id, request, headers, runtime
        )

        if response.body and response.body.data:
            return response.body.data.get("results", [])
        return []

    # ── 以下方法为兼容原接口，实际由百炼控制台管理 ──────────────────────────

    def add_documents(self, documents: List[Union[Document, str]], job_position_id: int = 0) -> int:
        """
        ⚠️ 注意：文档上传需在百炼控制台操作，或调用 create_knowledge_base 工具函数

        访问：https://bailian.console.aliyun.com/knowledge-base

        Args:
            documents: 文档列表（Document 对象或纯文本）
            job_position_id: 岗位分类（可用于元数据标记）

        Returns:
            0（占位，实际由控制台管理）
        """
        # 记录日志提示
        doc_count = len(documents) if isinstance(documents, (list, tuple)) else 1
        print(f"ℹ️  add_documents 被调用（{doc_count} 条），但百炼模式需在控制台上传文档")
        return 0

    def add_text(self, text: str, job_position_id: int = 0, source: str = "") -> int:
        """同上，控制台上传"""
        print(f"ℹ️  add_text 被调用，但百炼模式需在控制台上传文档: {source or '未知来源'}")
        return 0

    def delete_collection(self):
        """百炼知识库需在控制台删除"""
        print("ℹ️  请在百炼控制台管理知识库：https://bailian.console.aliyun.com/")

    def get_stats(self) -> dict:
        """返回基础信息"""
        return {
            "type": "aliyun_bailian_rag",
            "mode": self._mode,
            "knowledge_base_id": self.knowledge_base_id,
            "workspace_id": self.workspace_id if self._mode == "official_sdk" else None,
            "note": "文档管理请在百炼控制台操作: https://bailian.console.aliyun.com/knowledge-base"
        }


# ── 工具函数：创建知识库（封装官方 demo 流程）─────────────────────────────

def create_knowledge_base(
        file_path: str,
        name: str,
        workspace_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
        category_id: str = "default",
        parser: str = "DASHSCOPE_DOCMIND",
) -> Optional[str]:
    """
    使用阿里云百炼服务创建知识库（封装上传→解析→建索引流程）

    Args:
        file_path: 本地文件路径
        name: 知识库名称
        workspace_id: 业务空间 ID
        access_key_id: 阿里云 AccessKey ID
        access_key_secret: 阿里云 AccessKey Secret
        category_id: 类目 ID（默认 default）
        parser: 解析器类型（默认 DASHSCOPE_DOCMIND）

    Returns:
        知识库 ID（index_id），创建失败返回 None
    """
    if not _HAS_OFFICIAL_SDK:
        raise ImportError("创建知识库需要安装官方 SDK: pip install alibabacloud-bailian20231229")

    # 从环境变量读取配置（如果参数未传）
    workspace_id = workspace_id or os.getenv("BAILOU_WORKSPACE_ID")
    access_key_id = access_key_id or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
    access_key_secret = access_key_secret or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    if not all([workspace_id, access_key_id, access_key_secret]):
        raise ValueError("请配置 WORKSPACE_ID, ALIBABA_CLOUD_ACCESS_KEY_ID, ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    # 内部函数复用 demo 逻辑
    def _calc_md5(path: str) -> str:
        md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5.update(chunk)
        return md5.hexdigest()

    try:
        # 1. 初始化客户端
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            endpoint='bailian.cn-beijing.aliyuncs.com'
        )
        client = BailianClient(config)

        # 2. 准备文件信息
        file_name = os.path.basename(file_path)
        file_md5 = _calc_md5(file_path)
        file_size = os.path.getsize(file_path)

        # 3. 申请上传租约
        lease_req = bailian_models.ApplyFileUploadLeaseRequest(
            file_name=file_name,
            md_5=file_md5,
            size_in_bytes=file_size,
        )
        lease_resp = client.apply_file_upload_lease_with_options(
            category_id, workspace_id, lease_req, {}, util_models.RuntimeOptions()
        )
        lease_id = lease_resp.body.data.file_upload_lease_id
        upload_url = lease_resp.body.data.param.url
        upload_headers = lease_resp.body.data.param.headers

        # 4. 上传文件
        import requests
        with open(file_path, 'rb') as f:
            requests.put(
                upload_url,
                data=f.read(),
                headers={
                    "X-bailian-extra": upload_headers["X-bailian-extra"],
                    "Content-Type": upload_headers["Content-Type"]
                }
            )

        # 5. 添加文件到服务器
        add_req = bailian_models.AddFileRequest(
            lease_id=lease_id,
            parser=parser,
            category_id=category_id,
        )
        add_resp = client.add_file_with_options(workspace_id, add_req, {}, util_models.RuntimeOptions())
        file_id = add_resp.body.data.file_id

        # 6. 等待文件解析完成
        while True:
            desc_resp = client.describe_file_with_options(workspace_id, file_id, {}, util_models.RuntimeOptions())
            status = desc_resp.body.data.status
            if status == 'PARSE_SUCCESS':
                break
            elif status in ('PARSE_FAILED', 'ERROR'):
                raise RuntimeError(f"文件解析失败，状态: {status}")
            time.sleep(5)

        # 7. 创建知识库索引
        index_req = bailian_models.CreateIndexRequest(
            structure_type='unstructured',
            name=name,
            source_type='DATA_CENTER_FILE',
            sink_type='DEFAULT',
            document_ids=[file_id]
        )
        index_resp = client.create_index_with_options(workspace_id, index_req, {}, util_models.RuntimeOptions())
        index_id = index_resp.body.data.id

        # 8. 提交索引任务并等待完成
        submit_req = bailian_models.SubmitIndexJobRequest(index_id=index_id)
        submit_resp = client.submit_index_job_with_options(workspace_id, submit_req, {}, util_models.RuntimeOptions())
        job_id = submit_resp.body.data.id

        while True:
            status_resp = client.get_index_job_status_with_options(
                workspace_id,
                bailian_models.GetIndexJobStatusRequest(index_id=index_id, job_id=job_id),
                {},
                util_models.RuntimeOptions()
            )
            if status_resp.body.data.status == 'COMPLETED':
                break
            time.sleep(5)

        print(f"✅ 知识库创建成功！ID: {index_id}")
        return index_id

    except Exception as e:
        print(f"❌ 创建知识库失败: {e}")
        return None


# ── 工厂函数（保持原接口兼容）─────────────────────────────────────────────

def create_knowledge_store(
        db=None,
        api_key: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
) -> KnowledgeStore:
    """创建百炼知识库检索实例"""
    return KnowledgeStore(
        db=db,
        api_key=api_key,
        knowledge_base_id=knowledge_base_id,
        workspace_id=workspace_id,
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )