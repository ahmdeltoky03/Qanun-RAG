from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    APP_NAME: str = "Mini_RAG_App"
    APP_VERSION: str = "0.1.0"

    FILE_ALLOWED_TYPES: List[str]
    FILE_MAX_SIZE: int
    FILE_DEFAULT_CHUNK_SIZE: int

    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int 
    POSTGRES_MAIN_DATABASE: str
  
    GENERATION_BACKEND: str
    EMBEDDING_BACKEND: str

    OPEN_API_URL: Optional[str] = None
    OPEN_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None

    GENERATION_MODEL_ID_LITERAL: List[str]
    GENERATION_MODEL_ID: str 
    EMBEDDING_MODEL_ID: str 
    EMBEDDING_MODEL_SIZE: int

    DEFAULT_INPUT_MAX_CHARACTERS: Optional[int] = None
    DEFAULT_GENERATION_OUTPUT_TOKENS: Optional[int] = None
    DEFAULT_GENERATION_TEMPERATURE: Optional[float] = None
  
    VECTOR_DB_BACKEND_LITERAL: List[str]
    VECTOR_DB_BACKEND: str
    VECTOR_DB_PATH: str 
    VECTOR_DB_DISTANCE_METHOD: str
    VECTOR_DB_PGVEC_INDEX_THRESHOLD: int
  
    PRIMARY_LANG: str = "en"
    DEFAULT_LANG: str = "ar"
  
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  
        extra="ignore"
        )

def get_settings():
    return Settings()
