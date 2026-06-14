def main() -> None:
    from .chat import _ensure_profile, run_chat

    try:
        profile = _ensure_profile()
        run_chat(profile)
    except ValueError as e:
        print(f"\n配置错误: {e}")
    except Exception as e:
        print(f"\n发生错误: {e}")


if __name__ == "__main__":
    main()
