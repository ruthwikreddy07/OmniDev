import sys
import json
from pathlib import Path
from typing import Any
from src.mcp.codebase_tools import search_files, read_file_lines, apply_patch, get_file_tree
from src.mcp.test_runner import run_tests, run_command_sandboxed
from src.agent.tool_definitions import TOOL_DECLARATIONS


class MCPServer:
    """
    Standard Model Context Protocol (MCP) Server implementing JSON-RPC 2.0.
    Handles 'initialize', 'tools/list', and 'tools/call'.
    """

    def __init__(self, root_dir: str | Path = "."):
        self.root_dir = Path(root_dir).resolve()

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "omnidev-mcp-server", "version": "1.0.0"},
                    "capabilities": {"tools": {"listChanged": False}}
                }
            }

        elif method == "tools/list":
            mcp_tools = []
            for t in TOOL_DECLARATIONS:
                params_schema = t["parameters"]
                props = {
                    k: {"type": v["type"].lower(), "description": v.get("description", "")}
                    for k, v in params_schema.get("properties", {}).items()
                }
                mcp_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": {
                        "type": "object",
                        "properties": props,
                        "required": params_schema.get("required", [])
                    }
                })
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": mcp_tools}
            }

        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            try:
                content = self.call_tool(name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(content)}]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32000, "message": str(e)}
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"}
            }

    def _safe_path(self, fp: str) -> Path:
        full = (self.root_dir / fp).resolve()
        if not full.is_relative_to(self.root_dir):
            raise PermissionError(f"Access denied: path '{fp}' escapes workspace root")
        return full

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name == "search_files":
            return search_files(self.root_dir, args.get("query", ""))
        elif name == "read_file_lines":
            fp = self._safe_path(args.get("file_path", ""))
            return read_file_lines(fp, int(args.get("start_line") or 1), int(args.get("end_line") or 50))
        elif name == "apply_patch":
            fp = self._safe_path(args.get("file_path", ""))
            return apply_patch(fp, args.get("target_code", ""), args.get("replacement_code", ""))
        elif name == "run_tests":
            return run_tests(self.root_dir, args.get("test_command", "python -m pytest"))
        elif name == "get_file_tree":
            return get_file_tree(self.root_dir, int(args.get("max_depth") or 3))
        else:
            raise ValueError(f"Unknown tool: {name}")


def run_stdio_server():
    server = MCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = server.handle_request(req)
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
