"""PC방 로컬 브리지(bridge/lcu_bridge.py)가 보내주는 실시간 밴픽 상태를
연결된 프론트엔드(브라우저) 클라이언트들에게 WebSocket으로 중계한다.

개인용 도구라 방(room) 개념 없이 상태 하나만 전역으로 공유한다.
"""

from fastapi import WebSocket


class LiveHub:
    def __init__(self):
        self.state: dict = {"mode": "soloq", "actions": []}
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        await ws.send_json(self.state)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def push(self, state: dict):
        self.state = state
        dead = []
        for ws in self._clients:
            try:
                await ws.send_json(state)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


hub = LiveHub()
