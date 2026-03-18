from __future__ import annotations

try:
    import readline  # type: ignore[unused-import]  # noqa: F401
except Exception:
    pass

from app.graph_multi import run_once


def main() -> None:
    """命令行手动测试多 Agent 图（Quant + News 并行 -> CIO 调和）.

    运行: python -m tests.manual_run
    输入 exit 退出。
    """

    print("=== Multi-Agent Finance（Quant | News -> CIO）===" )
    print("输入问题，例如：分析一下 NVDA 或 BTC-USD 的走势与情绪")
    print("输入 'exit' 退出。\n")

    try:
        while True:
            user_input = input("你：").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                print("再见！")
                return

            print("Agent 运行中（Quant + News 并行，随后 CIO 综合）...", end="", flush=True)
            try:
                final_state = run_once(user_input)
            except Exception as exc:  # noqa: BLE001
                print()
                print(f"[错误] {type(exc).__name__}: {exc}")
                continue
            print()

            decision = final_state.get("final_decision") or ""
            if not decision:
                print("[提示] 未生成 final_decision，请检查 MINIMAX_API_KEY 与网络。")
                continue

            print("\n--- CIO 综合结论 ---\n")
            print(decision)

            # Quant/News 报告仅供 CIO 内部使用，如需调试可临时打印
            # final_state["quant_report"] 或 final_state["news_report"]。
            print()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
