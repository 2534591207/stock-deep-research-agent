"""配置 + 业务常量 + 启动期 fail-fast。

- 用 `pydantic-settings` 加载配置（自带 .env 读取，无需 python-dotenv）。
- `require_keys()` 在启动时校验核心 key，缺则 raise 并**只列出缺失 key 名（绝不打印值）**。
- 业务常量与 `spec.md §5.B` 字字一致。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根（.env 在这里：/agent/.env）；本文件在 /agent/backend/config.py
_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """从环境变量 / .env 加载配置。字段名小写，自动映射同名大写环境变量。"""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 核心 key（缺则启动 fail-fast）
    openai_api_key: Optional[str] = None
    twelve_data_api_key: Optional[str] = None
    # bonus key（事件 / 申报；不启用对应 bonus 时不纳入核心校验）
    tavily_api_key: Optional[str] = None
    sec_user_agent: Optional[str] = None
    # 可选：GitHub 图床（报告图表外链）。缺省不启用，绝不纳入 REQUIRED_KEYS，缺失不阻塞启动。
    github_token: Optional[str] = None
    github_image_repo: Optional[str] = None          # 形如 "owner/repo"
    github_image_branch: str = "report-assets"
    # LLM 模型
    openai_model: str = "gpt-4o-mini"

    @field_validator(
        "openai_api_key",
        "twelve_data_api_key",
        "tavily_api_key",
        "sec_user_agent",
        mode="before",
    )
    @classmethod
    def _clean_secret(cls, v: object) -> object:
        """清洗环境变量值：去掉两端空白与包裹引号（含中文全角 ＂＇ / 智能引号 “”‘’）。
        防止脏 key（如全角引号包裹）拼进 HTTP header 时 ASCII 编码失败导致 500。"""
        if not isinstance(v, str):
            return v
        v = v.strip()
        quote_chars = "\"'＂＇“”‘’`"
        while len(v) >= 2 and v[0] in quote_chars and v[-1] in quote_chars:
            v = v[1:-1].strip()
        # 兜底：API key / SEC UA 本应是纯 ASCII；剔除任何残留的非 ASCII 杂字符
        # （中文输入法的全角/智能引号、混入的中文字符等），避免拼进 HTTP header 时 500。
        if not v.isascii():
            v = "".join(ch for ch in v if ord(ch) < 128).strip()
        return v


settings = Settings()

# 核心必需 key（缺则拒绝启动）。**行情用 yfinance（Yahoo Finance，免费、无需 key）**；
# SEC / Tavily 为 bonus，仅启用对应 bonus 时才纳入。
REQUIRED_KEYS: tuple[str, ...] = ("OPENAI_API_KEY",)


def require_keys(s: "Settings | None" = None) -> None:
    """启动期校验核心 key。缺任一 → RuntimeError，消息**只含 key 名、不含值**。"""
    s = s if s is not None else settings
    present = {
        "OPENAI_API_KEY": s.openai_api_key,
    }
    missing = [name for name in REQUIRED_KEYS if not (present.get(name) or "").strip()]
    if missing:
        raise RuntimeError(
            "缺少必需的环境变量（请在 .env 配置）：" + ", ".join(missing)
        )


# ===== 业务常量（与 spec §5.B 一致；集中此处，不散落硬编码）=====

MAX_STOCKS = 3
MAX_RANGE_DAYS = 365
DEFAULT_RANGE_DAYS = 30
SIGNIFICANT_MOVE_MIN_PCT = 0.02
TRADING_DAYS_PER_YEAR = 252

# 风险打分
VOL_SCORE_CAP = 0.05           # 日波动率达 5% 记满分
DRAWDOWN_SCORE_CAP = 0.30      # 最大回撤达 30% 记满分
RISK_WEIGHT_VOL = 0.6
RISK_WEIGHT_DD = 0.4

# 绝对等级阈值（最严重优先，含边界）
RISK_THRESHOLDS = {
    "medium_volatility": 0.015,
    "high_volatility": 0.030,
    "medium_drawdown": 0.10,
    "high_drawdown": 0.20,
}

# Short-term Market View 阈值
RETURN_THRESHOLD_BASE = 0.05
RETURN_THRESHOLD_REF_DAYS = 21

# 数据充分性门槛
MIN_EFFECTIVE_TRADING_DAYS = 10
MIN_DATA_COVERAGE = 0.80
MIN_NEGATIVE_DAYS_FOR_VOL = 2

# ===== 文档上传 / RAG-lite 常量（新增功能；不进 REQUIRED_KEYS）=====
# 单文件财报上传 → 解析 → 内存向量检索 → grounded 问答。仅新增，不影响现有链路。
MAX_UPLOAD_MB = 15
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".txt", ".md")
DOC_CHUNK_CHARS = 2400          # 切块目标字符数（较大块 → 更少 chunk，首次嵌入更快）
DOC_CHUNK_OVERLAP = 250         # 相邻块重叠字符数
DOC_TOP_K = 6                   # 检索返回的相关块数
DOC_MAX_INDEX_CHARS = 1_000_000 # 最多嵌入的字符数（约一份完整 10-K，~482k 字符的 NVDA 样本可全量索引）；
                                # 仅极端超大文件（>1M 字符）才截断，超出部分不参与向量检索。
                                # 批量嵌入已足够快（~200+ chunk/上传可接受），故抬高上限以覆盖完整年报。
EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH_SIZE = 32           # 每批 embed_documents 的 chunk 数；分批 → 真实进度 + 避免单次超大慢请求
