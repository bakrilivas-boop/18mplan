"""
配置管理模块
"""
import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
TMP_CONFIG_FILE = os.path.join("/tmp", "config.json") if os.path.exists("/tmp") else CONFIG_FILE

_memory_config = {}

DEFAULT_CONFIG = {
    "proxy": "",
    "cookie": "",
    "threads": 8,
    "timeout": 10,
    "auto_system_proxy": True,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

def load_config() -> dict:
    global _memory_config
    if _memory_config:
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(_memory_config)
        return cfg

    config = DEFAULT_CONFIG.copy()
    target_path = TMP_CONFIG_FILE if os.path.exists(TMP_CONFIG_FILE) else CONFIG_FILE
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception:
            pass
    _memory_config = config.copy()
    return config

def save_config(new_config: dict) -> bool:
    global _memory_config
    config = load_config()
    config.update(new_config)
    _memory_config = config.copy()

    for p in [CONFIG_FILE, TMP_CONFIG_FILE]:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            continue
    return True
