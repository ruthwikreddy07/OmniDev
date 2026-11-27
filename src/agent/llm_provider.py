import os
import json
import urllib.request
import urllib.error
from typing import Any
from src.agent.tool_definitions import TOOL_DECLARATIONS


def _to_openai_tools() -> list[dict[str, Any]]:
    tools = []
    for t in TOOL_DECLARATIONS:
        params = t["parameters"]
        props = {
            k: {"type": v["type"].lower(), "description": v.get("description", "")}
            for k, v in params.get("properties", {}).items()
        }
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": params.get("required", []),
                },
            },
        })
    return tools


class LLMProvider:
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

        clean_explicit = (api_key or "").strip()
        if clean_explicit and not clean_explicit.startswith("•") and clean_explicit not in ("Not configured", "Managed by Server", "Configured in Session"):
            key = clean_explicit
            if key.startswith("gsk_"):
                self.provider = "groq"
                self.api_key = key
                self.model_name = model_name or "openai/gpt-oss-20b"
            else:
                self.provider = "gemini"
                self.api_key = key
                self.model_name = model_name or "gemini-2.0-flash"
        elif self.groq_key:
            self.provider = "groq"
            self.api_key = self.groq_key
            self.model_name = model_name or "openai/gpt-oss-20b"
        elif self.gemini_key:
            self.provider = "gemini"
            self.api_key = self.gemini_key
            self.model_name = model_name or "gemini-2.0-flash"
        else:
            self.provider = "mock"
            self.api_key = ""
            self.model_name = "mock"

        self.is_mock_mode = self.provider == "mock"

    def generate_content(
        self,
        conversation_history: list[dict[str, Any]],
        system_instruction: str
    ) -> dict[str, Any]:
        if self.provider == "mock":
            return self._mock_model_turn(conversation_history)
        if self.provider == "groq":
            return self._call_groq(conversation_history, system_instruction)
        return self._call_gemini(conversation_history, system_instruction)

    def _call_groq(
        self,
        conversation_history: list[dict[str, Any]],
        system_instruction: str
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]

        for idx, turn in enumerate(conversation_history):
            role = turn.get("role")
            parts = turn.get("parts", [])

            if role == "user":
                func_resp = next((p.get("functionResponse") for p in parts if "functionResponse" in p), None)
                if func_resp:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": f"call_{idx}",
                        "name": func_resp["name"],
                        "content": json.dumps(func_resp["response"]["content"]),
                    })
                else:
                    text = "\n".join(p["text"] for p in parts if "text" in p)
                    messages.append({"role": "user", "content": text})

            elif role == "model":
                text = "\n".join(p["text"] for p in parts if "text" in p)
                fc = next((p.get("functionCall") for p in parts if "functionCall" in p), None)
                msg: dict[str, Any] = {"role": "assistant", "content": text or None}
                if fc:
                    msg["tool_calls"] = [{
                        "id": f"call_{idx + 1}",
                        "type": "function",
                        "function": {
                            "name": fc["name"],
                            "arguments": json.dumps(fc.get("args", {})),
                        },
                    }]
                messages.append(msg)

        request_body = {
            "model": self.model_name,
            "messages": messages,
            "tools": _to_openai_tools(),
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "OmniDev/1.0",
            },
            method="POST",
        )

        import time
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                if e.code == 400 and "tool_use_failed" in body:
                    # Recover if Groq's gpt-oss model appended <|channel|>... to the tool name
                    try:
                        err_json = json.loads(body).get("error", {})
                        fg = json.loads(err_json.get("failed_generation", "") or "{}")
                        raw_name = fg.get("name", "")
                        clean_name = raw_name.split("<|")[0].strip()
                        if clean_name:
                            return {
                                "role": "model",
                                "parts": [{
                                    "functionCall": {
                                        "name": clean_name,
                                        "args": fg.get("arguments") if isinstance(fg.get("arguments"), dict) else {},
                                    }
                                }],
                            }
                    except Exception:
                        pass
                    if attempt < 3:
                        time.sleep(1)
                        continue
                if e.code == 429 and attempt < 3:
                    sleep_time = 4 * (attempt + 1)
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Groq API Error ({e.code}): {body}") from e

        choice = result["choices"][0]["message"]
        parts_out: list[dict[str, Any]] = []
        if choice.get("content"):
            parts_out.append({"text": choice["content"]})
        if choice.get("tool_calls"):
            tc = choice["tool_calls"][0]
            raw_args = tc["function"].get("arguments", "{}")
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                parsed_args = {}
            parts_out.append({
                "functionCall": {
                    "name": tc["function"]["name"].split("<|")[0].strip(),
                    "args": parsed_args,
                }
            })
        return {"role": "model", "parts": parts_out}

    def _call_gemini(
        self,
        conversation_history: list[dict[str, Any]],
        system_instruction: str
    ) -> dict[str, Any]:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )

        request_body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": conversation_history,
            "tools": [{"functionDeclarations": TOOL_DECLARATIONS}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
        }

        data = json.dumps(request_body).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                candidates = result.get("candidates", [])
                if not candidates:
                    raise RuntimeError("No candidates returned from API")
                return candidates[0].get("content", {})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"Gemini API Error ({e.code}): {body}") from e

    def _mock_model_turn(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        import time
        time.sleep(0.3)
        turn_count = len([m for m in history if m.get("role") == "model"])

        if turn_count == 0:
            return {
                "role": "model",
                "parts": [
                    {"text": "Searching for the buggy function in the codebase."},
                    {"functionCall": {"name": "search_files", "args": {"query": "calculate_discount"}}}
                ]
            }
        if turn_count == 1:
            return {
                "role": "model",
                "parts": [
                    {"text": "Found calculator.py. Reading the file to inspect the logic."},
                    {"functionCall": {"name": "read_file_lines", "args": {"file_path": "src/sample_app/calculator.py", "start_line": 1, "end_line": 50}}}
                ]
            }
        if turn_count == 2:
            return {
                "role": "model",
                "parts": [
                    {"text": "Found bug: division by zero when discount is 0. Applying patch."},
                    {"functionCall": {"name": "apply_patch", "args": {
                        "file_path": "src/sample_app/calculator.py",
                        "target_code": "        # BUG: Division by zero when discount_percent is 0\n        if discount_percent == 0:\n            return total_amount / 0\n",
                        "replacement_code": "        if discount_percent == 0:\n            return total_amount\n"
                    }}}
                ]
            }
        if turn_count == 3:
            return {
                "role": "model",
                "parts": [
                    {"text": "Running tests to verify the fix."},
                    {"functionCall": {"name": "run_tests", "args": {"test_command": "python -m unittest src.sample_app.test_calculator"}}}
                ]
            }
        return {
            "role": "model",
            "parts": [{"text": "Bug fixed and all tests passing. The ZeroDivisionError when discount_percent=0 has been resolved."}]
        }
