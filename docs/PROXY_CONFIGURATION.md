# 网络代理配置指南

Finance Agent 支持跨平台的智能代理配置，兼容 Windows、macOS、Linux 和 WSL2 环境。

## 快速开始

### 1. 不需要代理（默认）

如果你可以直连外网（如在美国、欧洲等地区），无需任何配置：

```bash
# .env 文件中
USE_PROXY=false
```

系统将直接连接 Binance API 和其他外部服务。

### 2. 需要代理（中国大陆、公司防火墙）

如果你在中国大陆或公司防火墙后，需要启用代理：

```bash
# .env 文件中
USE_PROXY=true
```

系统会自动探测你的环境并配置代理：

- **WSL2**: 自动探测 Windows 宿主机 IP
- **原生系统**: 使用 localhost (127.0.0.1:7890)

### 3. 手动指定代理地址

如果自动探测不工作，可以手动指定：

```bash
# .env 文件中
USE_PROXY=true
PROXY_URL=http://192.168.1.100:7890
```

## 配置选项

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| `USE_PROXY` | 是否启用代理 | `false` | `true` / `false` |
| `PROXY_URL` | 手动指定代理地址 | 自动探测 | `http://127.0.0.1:7890` |
| `PROXY_PORT` | 代理端口（仅在未设置 PROXY_URL 时使用） | `7890` | `7890` |

## 不同环境的配置示例

### Windows 原生

```bash
USE_PROXY=true
PROXY_URL=http://127.0.0.1:7890
```

### macOS

```bash
USE_PROXY=true
PROXY_URL=http://127.0.0.1:7890
```

### Linux 原生

```bash
USE_PROXY=true
PROXY_URL=http://127.0.0.1:7890
```

### WSL2（推荐使用自动探测）

```bash
# 自动探测 Windows 宿主机 IP
USE_PROXY=true

# 或手动指定
USE_PROXY=true
PROXY_URL=http://192.168.5.1:7890
```

## 常见代理软件端口

| 软件 | 默认端口 |
|------|---------|
| Clash | 7890 |
| V2Ray | 10808 |
| Shadowsocks | 1080 |
| Surge | 6152 |

## 故障排查

### 1. 连接超时

如果看到 "ConnectTimeout" 错误：

1. 检查代理软件是否运行
2. 确认代理端口是否正确
3. 检查防火墙设置

### 2. WSL2 无法连接

如果 WSL2 自动探测失败：

1. 手动获取 Windows IP：
   ```bash
   cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
   ```

2. 在 .env 中手动设置：
   ```bash
   USE_PROXY=true
   PROXY_URL=http://[上面获取的IP]:7890
   ```

### 3. 代理软件配置

确保代理软件允许局域网连接：

- **Clash**: 开启 "Allow LAN"
- **V2Ray**: 设置监听地址为 `0.0.0.0`

## 技术实现

代理配置由 `app/config/network.py` 模块处理，优先级如下：

1. `USE_PROXY=false` → 不使用代理
2. `PROXY_URL` 已设置 → 使用指定代理
3. WSL2 环境 → 自动探测宿主机 IP
4. 其他环境 → 使用 localhost

## 日志查看

启动时会显示代理配置信息：

```
INFO - Proxy disabled (USE_PROXY=false)
# 或
INFO - Using WSL2 auto-detected proxy: http://192.168.5.1:7890
# 或
INFO - Using localhost proxy: http://127.0.0.1:7890
```

## 相关文件

- `.env` - 用户配置文件
- `.env.example` - 配置模板
- `app/config/network.py` - 代理配置模块
- `app/services/binance_client.py` - 使用代理的客户端
