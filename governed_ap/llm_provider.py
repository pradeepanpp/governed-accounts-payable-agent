from typing import Protocol


class TextCompletionProvider(Protocol):
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...
