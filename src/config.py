from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class WebConfig(BaseModel):
    host: str = '127.0.0.1'
    port: int = 8001
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            'http://localhost:5173',
            'http://localhost:5174',
            'http://127.0.0.1:5173',
            'http://127.0.0.1:8001',
        ]
    )


class PathsConfig(BaseModel):
    data_dir: str = 'data/products'
    output_dir: str = 'outputs'
    database_path: str = 'runtime/app.db'


class JimengDefaults(BaseModel):
    mode: str = '视频生成'
    model: str = 'Seedance 2.0 Fast'
    reference_type: str = '全能参考'
    aspect_ratio: str = '9:16'


class VideoConfig(BaseModel):
    default_duration_seconds: Literal[5, 10, 15] = 10
    max_images: int = Field(default=3, ge=1)
    max_retries: int = Field(default=2, ge=0)
    task_timeout_seconds: int = Field(default=1800, ge=1)
    jimeng_defaults: JimengDefaults = Field(default_factory=JimengDefaults)


class JimengAccountConfig(BaseModel):
    name: str
    space_id: str = ''
    cdp_url: str | None = None
    web_port: int | None = None
    max_concurrent: int | None = Field(default=None, ge=1)


class JimengProviderConfig(BaseModel):
    enabled: bool = True
    base_url: str
    space_data_dir: str | None = None
    browser_executable_path: str | None = None
    cdp_url: str = 'http://127.0.0.1:9222'
    web_port: int = 3000
    default_concurrency: int = Field(default=10, ge=1)
    accounts: list[JimengAccountConfig] = Field(default_factory=list)


class ProvidersConfig(BaseModel):
    jimeng: JimengProviderConfig


class AuthConfig(BaseModel):
    secret_key: str = ""  # 留空则运行时从环境变量 JIMENG_SECRET_KEY 读取或自动生成
    token_expire_minutes: int = 480  # 8小时
    algorithm: str = "HS256"


class AppConfig(BaseModel):
    web: WebConfig = Field(default_factory=WebConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    providers: ProvidersConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)

    def resolve_path(self, value: str, config_path: str | Path | None = None) -> Path:
        expanded = Path(os.path.expandvars(value))
        if expanded.is_absolute() or config_path is None:
            return expanded
        return (Path(config_path).resolve().parent / expanded).resolve()


def load_config(config_path: str | Path = 'config.yaml') -> AppConfig:
    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists() and path.name == 'config.yaml':
        fallback = path.with_name('config.example.yaml')
        if fallback.exists():
            path = fallback

    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return AppConfig.model_validate(data)
