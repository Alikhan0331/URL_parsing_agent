import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    use_llm_fallback: bool = os.getenv("USE_LLM_FALLBACK", "true").lower() in ("1", "true", "yes")

    max_pages: int = int(os.getenv("MAX_PAGES", "5"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "15"))
    request_delay_seconds: float = float(os.getenv("REQUEST_DELAY_SECONDS", "1.5"))
    user_agent: str = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible; URLParsingAgent/1.0)")

    odoo_url: str = os.getenv("ODOO_URL", "")
    odoo_db: str = os.getenv("ODOO_DB", "")
    odoo_username: str = os.getenv("ODOO_USERNAME", "")
    odoo_password: str = os.getenv("ODOO_PASSWORD", "")


settings = Settings()
