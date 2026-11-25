TOOL_DECLARATIONS = [
    {
        "name": "search_files",
        "description": "Recursively search the codebase for files by filename or text content match.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search term to find in filenames or file contents."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file_lines",
        "description": "Read specific line range from a file with line numbers. Always read before patching.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "Relative path to the file."},
                "start_line": {"type": "INTEGER", "description": "Start line (1-based). Default 1."},
                "end_line": {"type": "INTEGER", "description": "End line (inclusive). Default 50."},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "apply_patch",
        "description": "Replace an exact code block in a file with new code. Target must match exactly.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "Path of file to modify."},
                "target_code": {"type": "STRING", "description": "Exact existing code to replace."},
                "replacement_code": {"type": "STRING", "description": "New code to insert."},
            },
            "required": ["file_path", "target_code", "replacement_code"],
        },
    },
    {
        "name": "run_tests",
        "description": "Execute the project test suite and return pass/fail status with output.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "test_command": {"type": "STRING", "description": "Shell command to run tests. Default: python -m pytest."},
            },
            "required": [],
        },
    },
    {
        "name": "get_file_tree",
        "description": "List all files and directories in the project tree.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_depth": {"type": "INTEGER", "description": "Maximum directory depth. Default 3."},
            },
            "required": [],
        },
    },
]
