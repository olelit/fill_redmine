from dataclasses import dataclass, field


@dataclass
class AiSettings:
    provider: str = "opencode_go"
    model: str = "deepseek-v4.1-flash"
    base_url: str = ""
    keys: dict[str, str] = field(default_factory=dict)

    def key_for(self, provider: str) -> str:
        return self.keys.get(provider, "")
