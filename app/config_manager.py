"""Configuration manager for handling .env file updates."""
import os
from pathlib import Path
from typing import Dict, Optional


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


# Global instance
config_manager = ConfigManager()
