import shutil
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    # Storage
    storage_root: Path = BACKEND_ROOT / "storage"
    database_path: Path = BACKEND_ROOT / "data" / "app.db"

    # Upload constraints (FR-01)
    max_upload_size_bytes: int = 20 * 1024 * 1024  # 20 MB default
    allowed_extensions: tuple[str, ...] = (".pdf", ".jpg", ".jpeg", ".png")
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "image/jpeg",
        "image/png",
    )

    # OCR toolchain (local, pre-installed on this machine)
    tesseract_cmd: str = r"C:\Users\91981\Tesseract-OCR\tesseract.exe"
    poppler_path: str = r"C:\Users\91981\poppler-24.08.0\Library\bin"
    ocr_language: str = "eng"
    ocr_processor_name: str = "pytesseract"
    ocr_processor_version: str = "5.5.0"

    # Server (localhost only, per TRD security architecture)
    host: str = "127.0.0.1"
    port: int = 8000
    cors_allow_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )

    # Business defaults
    default_currency: str = "INR"
    low_confidence_threshold: float = 0.75

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def images_dir(self) -> Path:
        return self.storage_root / "images"

    @property
    def generated_dir(self) -> Path:
        return self.storage_root / "generated"

    @property
    def temp_dir(self) -> Path:
        return self.storage_root / "temp"

    def resolved_tesseract_cmd(self) -> str:
        if Path(self.tesseract_cmd).exists():
            return self.tesseract_cmd
        found = shutil.which("tesseract")
        if found:
            return found
        raise RuntimeError(
            "Tesseract binary not found. Set APP_TESSERACT_CMD to its full path."
        )

    def resolved_poppler_path(self) -> str | None:
        if Path(self.poppler_path).exists():
            return self.poppler_path
        return None  # pdf2image will fall back to PATH lookup

    def ensure_storage_dirs(self) -> None:
        for d in (self.uploads_dir, self.images_dir, self.generated_dir, self.temp_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
