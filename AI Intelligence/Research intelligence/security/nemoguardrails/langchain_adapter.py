from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration

import llm_providers
from llm_providers import ChatMessage, ChatRequest
from security.nemoguardrails import observability


class RouterChatModel(BaseChatModel):
    """Bridges the shared ProviderRouter into LangChain so NeMo Guardrails can use it."""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # Dynamic lookup ensures monkeypatching in tests works correctly
        router = llm_providers.get_router()
        router_messages = []
        for m in messages:
            role = "system" if isinstance(m, SystemMessage) else ("assistant" if isinstance(m, AIMessage) else "user")
            router_messages.append(ChatMessage(role=role, content=m.content))
        try:
            resp = router.complete(ChatRequest(messages=router_messages))
        except Exception:
            # Graceful degradation: return a safe fallback message instead of crashing the NeMo runtime
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="I am currently unable to process your request due to a service issue. Please try again later."
            ))])
            
        llm_output = None
        if resp.usage:
            llm_output = {"token_usage": {"prompt_tokens": resp.usage.prompt_tokens,
                                          "completion_tokens": resp.usage.completion_tokens,
                                          "total_tokens": resp.usage.total_tokens},
                          "model_name": resp.model, "provider": resp.provider}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=resp.content))],
                          llm_output=llm_output)

    def _config_with_callbacks(self, config):
        handler = observability.get_langfuse_handler()
        if handler is None:
            return config
        config = dict(config or {})
        config["callbacks"] = list(config.get("callbacks") or []) + [handler]
        return config

    def invoke(self, input, config=None, **kwargs):
        return super().invoke(input, self._config_with_callbacks(config), **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        return await super().ainvoke(input, self._config_with_callbacks(config), **kwargs)

    @property
    def _llm_type(self):
        return "router_chat_model"