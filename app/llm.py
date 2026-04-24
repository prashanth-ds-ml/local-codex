from langchain_ollama import ChatOllama


def get_chat_llm() -> ChatOllama:
    """Chat and code tasks — qwen2.5-coder specialised for code generation."""
    return ChatOllama(model="qwen2.5-coder:7b", temperature=0.2)


def get_agent_llm() -> ChatOllama:
    """Agent and tool-use tasks — qwen3.5 with reliable structured tool calling."""
    return ChatOllama(model="qwen3.5:latest", temperature=0)


# backwards-compat alias used by older call sites
def get_llm() -> ChatOllama:
    return get_chat_llm()
