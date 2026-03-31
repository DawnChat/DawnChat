from __future__ import annotations

from typing import Any, AsyncIterator, Dict

from app.agentv3.runtime.stream_consumer import RuntimeStreamConsumer


class RuntimeStepProcessor:
    def __init__(self, owner):
        self._stream = RuntimeStreamConsumer(owner)

    async def run_single_stream_step(
        self,
        run_input: Any,
        model_messages,
        step_state: Dict[str, Any],
        *,
        is_last_step: bool = False,
        step_hint: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        async for event in self._stream.run_single_stream_step(
            run_input=run_input,
            model_messages=model_messages,
            step_state=step_state,
            is_last_step=is_last_step,
            step_hint=step_hint,
        ):
            yield event
