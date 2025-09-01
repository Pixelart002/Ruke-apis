import requests, json, os

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "ai_registry.json")

def load_registry():
    try:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def query_ai_from_registry(tool_name: str, user_message: str, model: str = None, timeout: int = 10):
    registry = load_registry()
    tool = None
    if isinstance(registry, dict):
        if "tools" in registry and tool_name in registry["tools"]:
            tool = registry["tools"][tool_name]
        elif tool_name in registry:
            tool = registry[tool_name]
        else:
            for k, v in registry.items():
                if isinstance(v, dict) and tool_name in v:
                    tool = v[tool_name]
                    break
    if not tool:
        return {"error": f"Tool '{tool_name}' not found"}
    endpoint = tool.get("endpoint")
    default_model = tool.get("default_model") or model
    params = {"user": user_message}
    if default_model:
        params["model"] = default_model
    try:
        resp = requests.get(endpoint, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}