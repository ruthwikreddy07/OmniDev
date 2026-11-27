import json
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, ws: WebSocket):
        await ws.accept()
        if job_id not in self.connections:
            self.connections[job_id] = []
        self.connections[job_id].append(ws)

    def disconnect(self, job_id: str, ws: WebSocket):
        if job_id in self.connections:
            self.connections[job_id] = [c for c in self.connections[job_id] if c != ws]
            if not self.connections[job_id]:
                self.connections.pop(job_id, None)

    async def broadcast(self, job_id: str, data: dict):
        conns = list(self.connections.get(job_id, []))
        if not conns:
            return
        message = json.dumps(data)
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead and job_id in self.connections:
            self.connections[job_id] = [c for c in self.connections[job_id] if c not in dead]
            if not self.connections[job_id]:
                self.connections.pop(job_id, None)


ws_manager = WebSocketManager()
