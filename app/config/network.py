"""Network configuration module with intelligent proxy detection.

This module provides cross-platform proxy configuration support for:
- Native Windows, macOS, Linux (direct connection or localhost proxy)
- WSL2 (automatic host IP detection)
- Manual proxy configuration via environment variables

Configuration priority:
1. USE_PROXY=false -> No proxy (direct connection)
2. PROXY_URL set -> Use specified proxy
3. WSL2 detected -> Auto-detect Windows host IP
4. Fallback -> Use localhost:7890
"""

import logging
import os
import platform
from typing import Optional

from dotenv import load_dotenv

# Load .env file before reading environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def is_wsl2() -> bool:
    """Detect if running in WSL2 environment.

    Returns:
        True if running in WSL2, False otherwise
    """
    try:
        # Check kernel release for WSL2 signature
        release = platform.uname().release.lower()
        return "microsoft" in release or "wsl" in release
    except Exception:
        return False


def get_wsl2_host_ip() -> Optional[str]:
    """Get Windows host IP from WSL2 environment.

    Reads /etc/resolv.conf to find the nameserver (Windows host IP).

    Returns:
        Host IP address or None if detection fails
    """
    try:
        with open("/etc/resolv.conf", "r") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    host_ip = line.split()[1]
                    logger.info(f"Detected WSL2 host IP: {host_ip}")
                    return host_ip
    except Exception as e:
        logger.warning(f"Failed to detect WSL2 host IP: {e}")
    return None


def get_proxy_url() -> Optional[str]:
    """Get proxy URL with intelligent detection.

    Configuration priority:
    1. If USE_PROXY=false, return None (no proxy)
    2. If PROXY_URL is set, use it
    3. If WSL2 detected, auto-detect host IP
    4. Fallback to localhost:7890

    Environment variables:
    - USE_PROXY: "true" or "false" (default: "false")
    - PROXY_URL: Manual proxy URL (e.g., "http://127.0.0.1:7890")
    - PROXY_PORT: Proxy port (default: 7890)

    Returns:
        Proxy URL string or None if proxy is disabled
    """
    # Check if proxy is enabled
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"

    if not use_proxy:
        logger.info("Proxy disabled (USE_PROXY=false)")
        return None

    # Check for manual proxy configuration
    manual_proxy = os.getenv("PROXY_URL")
    if manual_proxy:
        logger.info(f"Using manual proxy: {manual_proxy}")
        return manual_proxy

    # Get proxy port from environment or use default
    proxy_port = os.getenv("PROXY_PORT", "7890")

    # Auto-detect for WSL2
    if is_wsl2():
        host_ip = get_wsl2_host_ip()
        if host_ip:
            proxy_url = f"http://{host_ip}:{proxy_port}"
            logger.info(f"Using WSL2 auto-detected proxy: {proxy_url}")
            return proxy_url
        else:
            logger.warning("WSL2 detected but failed to get host IP, falling back to localhost")

    # Fallback to localhost
    proxy_url = f"http://127.0.0.1:{proxy_port}"
    logger.info(f"Using localhost proxy: {proxy_url}")
    return proxy_url


# Global proxy configuration
PROXY_URL = get_proxy_url()
