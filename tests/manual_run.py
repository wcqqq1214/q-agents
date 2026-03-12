from __future__ import annotations

from typing import NoReturn

try:
    # Enable line-editing features (Backspace, history) for input() where available.
    import readline  # type: ignore[unused-import]  # noqa: F401
except Exception:
    # In environments without readline support, fall back silently.
    pass

from app.graph import run_once


def main() -> NoReturn:
    """简单的命令行测试脚本，用于手动验证金融 Agent。

    运行方式（在项目根目录）::

        python -m tests.manual_run

    脚本会循环读取用户输入，将其发送给 LangGraph 构建的金融 Agent，
    并打印模型最终回复。输入 ``exit`` 或按 Ctrl+C 可退出。
    """

    print("=== Finance Agent 手动测试 ===")
    print("输入你的问题，例如：AAPL 的股价和最近新闻？")
    print("输入 'exit' 退出。\n")

    try:
        while True:
            user_input = input("你：").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                print("再见！")
                return

            print("Agent 思考中...", end="", flush=True)
            try:
                messages = run_once(user_input)
            except Exception as exc:  # noqa: BLE001
                print()
                print(f"[错误] 调用 Agent 失败: {type(exc).__name__}: {exc}")
                continue
            print()

            # 打印最后一条 AI 回复（如果有）
            ai_messages = [m for m in messages if getattr(m, "type", "") == "ai"]
            if not ai_messages:
                print("[提示] 本轮没有生成 AI 回复，请检查日志或工具调用。")
                continue

            last_ai = ai_messages[-1]
            print("\nAgent：", last_ai.content, "\n")
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()

