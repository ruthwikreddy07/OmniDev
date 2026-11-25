from pathlib import Path
from typing import Any, Callable
from src.mcp.codebase_tools import search_files, read_file_lines, apply_patch, get_file_tree
from src.mcp.test_runner import run_tests
from src.agent.llm_provider import LLMProvider


class AgentExecutor:
    def __init__(self, llm_provider: LLMProvider, project_dir: str = ".", max_iterations: int = 8):
        self.llm = llm_provider
        self.project_dir = Path(project_dir).resolve()
        self.max_iterations = max_iterations
        self.system_instruction = (
            "You are OmniDev, an autonomous software engineer. "
            "Investigate bugs, search files, read code, apply patches, and run tests. "
            "Always search before guessing. Read code before patching. Run tests after patching to verify."
        )
        self.logs: list[dict[str, str]] = []
        self.diffs: list[dict[str, Any]] = []

    def _log(self, event: str, data: str, on_step: Callable | None = None):
        entry = {"event": event, "data": data}
        self.logs.append(entry)
        if on_step:
            on_step(entry)

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "search_files":
            results = search_files(self.project_dir, args.get("query", ""))
            return {"match_count": len(results), "matches": results}

        elif tool_name == "read_file_lines":
            fp = args.get("file_path", "")
            full = self.project_dir / fp
            return {"file_path": fp, "content": read_file_lines(full, int(args.get("start_line", 1)), int(args.get("end_line", 50)))}

        elif tool_name == "apply_patch":
            fp = args.get("file_path", "")
            full = self.project_dir / fp
            result = apply_patch(full, args.get("target_code", ""), args.get("replacement_code", ""))
            self.diffs.append({
                "file_path": fp,
                "diff": result.get("diff", ""),
                "new_content": result.get("new_content", "")
            })
            return result

        elif tool_name == "run_tests":
            cmd = args.get("test_command", "python -m pytest")
            return run_tests(self.project_dir, cmd)

        elif tool_name == "get_file_tree":
            return {"tree": get_file_tree(self.project_dir, int(args.get("max_depth", 3)))}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def run(self, task: str, on_step: Callable | None = None) -> dict[str, Any]:
        self.logs = []
        self.diffs = []
        self._log("task", task, on_step)
        self._log("mode", "mock" if self.llm.is_mock_mode else f"live ({self.llm.provider})", on_step)

        history: list[dict[str, Any]] = [
            {"role": "user", "parts": [{"text": task}]}
        ]

        for iteration in range(1, self.max_iterations + 1):
            self._log("turn", f"{iteration}/{self.max_iterations}", on_step)

            model_content = self.llm.generate_content(history, self.system_instruction)
            history.append(model_content)

            parts = model_content.get("parts", [])
            texts = [p["text"] for p in parts if "text" in p]
            for t in texts:
                self._log("thought", t, on_step)

            fc = next((p.get("functionCall") for p in parts if "functionCall" in p), None)
            if not fc:
                final_text = "\n".join(texts)
                self._log("done", final_text, on_step)
                final_status = "awaiting_approval" if self.diffs else "completed"
                return {
                    "status": final_status,
                    "result": final_text,
                    "iterations": iteration,
                    "logs": self.logs,
                    "diffs": self.diffs
                }

            tool_name = fc["name"]
            tool_args = fc.get("args", {})
            self._log("tool_call", f"{tool_name}: {tool_args}", on_step)

            try:
                tool_result = self.execute_tool(tool_name, tool_args)
                self._log("tool_result", str(tool_result)[:500], on_step)
            except Exception as e:
                tool_result = {"error": str(e)}
                self._log("tool_error", str(e), on_step)

            history.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": tool_name, "response": {"content": tool_result}}}]
            })

        return {
            "status": "max_iterations_reached",
            "result": None,
            "iterations": self.max_iterations,
            "logs": self.logs,
            "diffs": self.diffs
        }
