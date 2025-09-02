import requests
from fastapi import HTTPException

# 🚀 Ultra God AI Registry with Plans
AI_REGISTRY = {
    # ------------------- CHAT -------------------
    "qwen": {
        "name": "Qwen Chat",
        "type": "chat",
        "base_url": "https://qwen.a3z.workers.dev/api",
        "auth": None,
        "endpoints": {
            "new": "/new",
            "completions": "/completions"
        },
        "cost": 0,
        "access": "normal"
    },

    "mistral": {
        "name": "Mistral Chat",
        "type": "chat",
        "base_url": "https://mistral-ai-three.vercel.app",
        "auth": None,
        "endpoints": {
            "ask": "/?id={user_id}&question={question}"
        },
        "cost": 0.002,
        "access": "premium"
    },

    # ------------------- IMAGE -------------------
    "flux_schnell": {
        "name": "Flux-Schnell",
        "type": "image",
        "base_url": "https://flux-schnell.hello-kaiiddo.workers.dev",
        "auth": None,
        "endpoints": {
            "img": "/img?prompt={prompt}&model={model}&guidance={guidance}&strength={strength}"
        },
        "cost": 0.005,
        "access": "premium"
    },

    # ------------------- SEARCH -------------------
    "search": {
        "name": "OpenAI Search",
        "type": "search",
        "base_url": "https://search.hello-kaiiddo.workers.dev",
        "auth": None,
        "endpoints": {
            "query": "/search?q={query}"
        },
        "cost": 0,
        "access": "normal"
    },

    # ------------------- VOICE -------------------
    "voice_assistant": {
        "name": "OpenAI Voice Assistant",
        "type": "voice",
        "base_url": "https://voice-assistance.hello-kaiiddo.workers.dev",
        "auth": None,
        "endpoints": {
            "speak": "/{text}?model=openai-audio&voice={voice}"
        },
        "voices": [
            "nova", "alloy", "echo", "fable", "onyx", "shimmer", "coral",
            "verse", "ballad", "ash", "sage", "amuch", "dan"
        ],
        "cost": 0.003,
        "access": "premium"
    },

    # ------------------- TEXT GENERATION -------------------
    "text_generation": {
        "name": "System Prompt Text Generation",
        "type": "text",
        "base_url": "https://text.hello-kaiiddo.workers.dev",
        "auth": None,
        "endpoints": {
            "generate": "/generate?q={prompt}&model={model}&seed={seed}&system={system}"
        },
        "params": ["prompt", "model", "seed", "system"],
        "cost": 0,
        "access": "normal"
    }
}


def query_ai_from_registry(tool_name: str, user_message: str, user_id: str, model: str = None):
    """Query any AI tool from the registry"""

    if tool_name not in AI_REGISTRY:
        raise HTTPException(status_code=404, detail="Tool not found in registry")

    tool = AI_REGISTRY[tool_name]

    # 🛑 Example: Access Control (premium check)
    if tool["access"] == "premium" and not user_id.startswith("premium_"):
        raise HTTPException(status_code=403, detail="This tool is only available for Premium users")

    base_url = tool["base_url"]

    # Example endpoint handling
    if tool_name == "mistral":
        url = base_url + tool["endpoints"]["ask"].format(user_id=user_id, question=user_message)
        response = requests.get(url)
        return response.json()

    elif tool_name == "qwen":
        url = base_url + tool["endpoints"]["completions"]
        payload = {"prompt": user_message, "model": model or "default"}
        response = requests.post(url, json=payload)
        return response.json()

    elif tool_name == "search":
        url = base_url + tool["endpoints"]["query"].format(query=user_message)
        response = requests.get(url)
        return response.json()

    elif tool_name == "text_generation":
        url = base_url + tool["endpoints"]["generate"].format(
            prompt=user_message, model=model or "default", seed=42, system="UltraGodAI"
        )
        response = requests.get(url)
        return response.json()

    elif tool_name == "voice_assistant":
        url = base_url + tool["endpoints"]["speak"].format(text=user_message, voice="nova")
        response = requests.get(url)
        return {"voice_url": url, "raw": response.text}

    elif tool_name == "flux_schnell":
        url = base_url + tool["endpoints"]["img"].format(
            prompt=user_message, model=model or "flux-schnell", guidance=7, strength=0.8
        )
        response = requests.get(url)
        return {"image_url": url, "raw": response.text}

    else:
        raise HTTPException(status_code=400, detail="Tool not implemented yet")