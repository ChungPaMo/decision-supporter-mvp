from typing import Literal

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from contracts.interfaces.dataset import DatasetId
from contracts.interfaces.xlsx import Sha256


class Settings(BaseSettings):
    # Compose와 같은 루트 .env를 실행 디렉터리에 관계없이 읽는다.
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")

    # 로컬 개발용 기본값(compose.yaml 의 전용 컨테이너, 127.0.0.1 한정). 공유·운영 환경은 반드시 .env 로 덮어쓴다.
    database_url: str = "postgresql+psycopg://chungpamo_app:change_me_app_dev_only@127.0.0.1:55433/chungpamo"
    app_version: str = "0.1.0"
    # 배치 저장(업로드 보관·승인·조회) API. 기본은 꺼짐: DB 통합이 검증되기 전에는 영구 저장을 하는 척하지 않는다.
    # 'postgres'는 SQL 저장소를 사용한다. 기존 소스의 검증과 새 환경의 재검증 결과는 구분한다.
    persistence: Literal["disabled", "postgres"] = "disabled"
    # 쉼표로 구분한 브라우저 허용 출처 (예: http://localhost:5173). 비우면 CORS 를 켜지 않는다. '*' 는 허용하지 않는다.
    cors_allow_origins: str = ""

    upstage_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    upstage_api_enabled: bool = False
    ai_external_data_allowed: bool = False
    # The deployment operator must attest that every listed source is synthetic.
    ai_external_synthetic_sources: dict[DatasetId, frozenset[Sha256]] = Field(default_factory=dict)
    ai_mapping_enabled: bool = False
    ai_embedding_enabled: bool = False
    document_parse_enabled: bool = False
    information_extract_enabled: bool = False
    document_classify_enabled: bool = False
    document_ocr_enabled: bool = False
    ai_mapping_model: str = 'solar-mini4-260922'
    ai_mapping_strategy: Literal['hold_review', 'direct', 'concept', 'business', 'verify_candidates'] = 'hold_review'
    ai_mapping_prompt_version: str = 'mapping-v1'
    ai_mapping_knowledge_version: str = 'manufacturing-v1'
    ai_mapping_timeout_seconds: float = Field(default=30, gt=0, le=180, allow_inf_nan=False)
    ai_mapping_max_columns: int = Field(default=32, ge=1, le=64)
    ai_mapping_max_input_bytes: int = Field(default=131072, ge=1024, le=1048576)
    upstage_max_response_bytes: int = Field(default=1048576, ge=1024, le=8388608)
    upstage_document_max_input_bytes: int = Field(default=2097152, ge=1024, le=10485760)
    upstage_document_parse_model: str = 'document-parse-260930'
    upstage_document_parse_mode: Literal['standard', 'enhanced', 'auto'] = 'standard'
    upstage_information_extract_model: str = 'information-extract-261113'
    upstage_information_extract_mode: Literal['standard', 'enhanced'] = 'standard'
    upstage_document_classify_model: str = 'document-classify-261113'

    def cors_origins(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in self.cors_allow_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ALLOW_ORIGINS 에 '*' 는 쓸 수 없습니다. 출처를 명시하세요.")
        return origins


def get_settings() -> Settings:
    return Settings()
