"""Configuration manager for handling .env file updates."""
import os
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manages configuration updates to .env file."""

    def __init__(self, env_path: Optional[Path] = None):
        """Initialize config manager.

        Args:
            env_path: Path to .env file. Defaults to .env in project root.
        """
        if env_path is None:
            # Get project root (parent of app directory)
            project_root = Path(__file__).parent.parent
            env_path = project_root / ".env"

        self.env_path = env_path

    def mask_api_key(self, key: str) -> str:
        """Mask API key for display.

        Args:
            key: The API key to mask

        Returns:
            Masked key showing first 3 and last 4 characters
        """
        if not key or len(key) < 8:
            return "***"
        return f"{key[:3]}***{key[-4:]}"

    def get_settings(self) -> Dict[str, Optional[str]]:
        """Get current settings with full API keys.

        Returns:
            Dictionary of API keys
        """
        settings = {
            "claude_api_key": os.getenv("CLAUDE_API_KEY"),
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "polygon_api_key": os.getenv("POLYGON_API_KEY"),
            "tavily_api_key": os.getenv("TAVILY_API_KEY"),
        }

        return settings

    def update_settings(self, updates: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        """Update settings in .env file.

        Args:
            updates: Dictionary of settings to update

        Returns:
            Updated settings with masked keys
        """
        # Filter out None values and empty strings
        updates = {k: v for k, v in updates.items() if v}

        if not updates:
            return self.get_settings()

        # Convert keys to uppercase for .env file
        env_updates = {k.upper(): v for k, v in updates.items()}

        # Update .env file
        self._update_env_file(env_updates)

        # Update runtime environment
        for key, value in env_updates.items():
            os.environ[key] = value

        # Return masked settings
        return self.get_settings()

    def _update_env_file(self, updates: Dict[str, str]) -> None:
        """Update .env file with new values.

        Args:
            updates: Dictionary of environment variables to update
        """
        if not self.env_path.exists():
            # Create new .env file
            lines = [f"{key}={value}" for key, value in updates.items()]
            self.env_path.write_text("\n".join(lines) + "\n")
            return

        # Read existing file
        lines = self.env_path.read_text().splitlines()
        updated_keys = set()

        # Update existing keys
        for i, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            for key, value in updates.items():
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    updated_keys.add(key)
                    break

        # Add new keys that weren't found
        for key, value in updates.items():
            if key not in updated_keys:
                lines.append(f"{key}={value}")

        # Write back to file
        self.env_path.write_text("\n".join(lines) + "\n")

    def get_okx_settings(self, mode: str = "demo") -> Dict[str, Optional[str]]:
        """获取OKX配置

        Args:
            mode: 模式 (live/demo)

        Returns:
            OKX配置字典

        Raises:
            ValueError: 如果mode不是'live'或'demo'
        """
        if mode not in ("live", "demo"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'live' or 'demo'")

        prefix = f"OKX_{mode.upper()}_"
        return {
            "api_key": os.getenv(f"{prefix}API_KEY"),
            "secret_key": os.getenv(f"{prefix}SECRET_KEY"),
            "passphrase": os.getenv(f"{prefix}PASSPHRASE"),
            "mode": mode,
        }

    def update_okx_settings(
        self,
        mode: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """更新OKX配置

        Args:
            mode: 模式 (live/demo)
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码

        Returns:
            更新后的配置

        Raises:
            ValueError: 如果mode不是'live'或'demo'
        """
        if mode not in ("live", "demo"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'live' or 'demo'")

        prefix = f"OKX_{mode.upper()}_"
        updates = {}
        if api_key:
            updates[f"{prefix}API_KEY"] = api_key
        if secret_key:
            updates[f"{prefix}SECRET_KEY"] = secret_key
        if passphrase:
            updates[f"{prefix}PASSPHRASE"] = passphrase

        if updates:
            self._update_env_file(updates)

            # 更新运行时环境
            for key, value in updates.items():
                os.environ[key] = value

        return self.get_okx_settings(mode)

    def get_redis_settings(self) -> Dict[str, Any]:
        """获取 Redis 配置"""
        return {
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            "redis_enabled": os.getenv("REDIS_ENABLED", "true").lower() == "true",
            "max_connections": int(os.getenv("REDIS_MAX_CONNECTIONS", "100")),
            "socket_timeout": int(os.getenv("REDIS_SOCKET_TIMEOUT", "2")),
            "socket_connect_timeout": int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "2")),
            "pool_timeout": int(os.getenv("REDIS_POOL_TIMEOUT", "1")),
            "health_check_interval": int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
        }

    def update_redis_settings(
        self,
        redis_url: Optional[str] = None,
        redis_enabled: Optional[bool] = None
    ) -> Dict[str, Any]:
        """更新 Redis 配置"""
        updates = {}
        if redis_url:
            updates["REDIS_URL"] = redis_url
        if redis_enabled is not None:
            updates["REDIS_ENABLED"] = "true" if redis_enabled else "false"

        if updates:
            self._update_env_file(updates)
            for key, value in updates.items():
                os.environ[key] = value

        return self.get_redis_settings()


def get_stock_catchup_config() -> dict:
    """Get stock catch-up configuration from environment variables.

    Returns:
        dict with keys:
            - catchup_days: int - Maximum days to look back
            - rate_limit_delay: float - Delay between requests in seconds
            - enabled: bool - Whether catch-up is enabled
    """
    return {
        "catchup_days": int(os.getenv("STOCK_CATCHUP_DAYS", "5")),
        "rate_limit_delay": float(os.getenv("STOCK_RATE_LIMIT_DELAY", "1.5")),
        "enabled": os.getenv("STOCK_CATCHUP_ENABLED", "true").lower() == "true"
    }


# Global instance
config_manager = ConfigManager()
