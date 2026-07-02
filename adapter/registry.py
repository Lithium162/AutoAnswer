from __future__ import annotations

from .base import ScriptAdapter


class AdapterRegistry:
    """适配器注册表 — 按名字找到对应的适配器类并实例化

    用法:
        AdapterRegistry.register("baas", BAASAdapter)
        adapter = AdapterRegistry.create("baas", api_url="http://127.0.0.1:37421")
    """

    _adapters: dict[str, type[ScriptAdapter]] = {}

    @classmethod
    def register(cls, name: str, adapter_cls: type[ScriptAdapter]) -> None:
        """注册一个适配器类"""
        cls._adapters[name] = adapter_cls

    @classmethod
    def create(cls, name: str, **kwargs) -> ScriptAdapter:
        """按名字创建适配器实例，传入的 kwargs 透传给构造函数"""
        if name not in cls._adapters:
            raise ValueError(
                f"Unknown script '{name}'. "
                f"Available: {', '.join(cls._adapters)}"
            )
        return cls._adapters[name](**kwargs)

    @classmethod
    def registered(cls) -> list[str]:
        """返回所有已注册的适配器名字"""
        return list(cls._adapters.keys())
