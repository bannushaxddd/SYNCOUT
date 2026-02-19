"""
SYNCOUT - Real-time Collaborative Code Editor
Backend: FastAPI + WebSockets + Operational Transform
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio
import uuid
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging
import os
from .executor import executor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SYNCOUT", description="Real-time Collaborative Code Editor")

@app.get("/health")
async def health():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class Operation:
    type: str
    position: int
    content: str = ""
    length: int = 0
    user_id: str = ""
    revision: int = 0
    timestamp: float = field(default_factory=time.time)

@dataclass
class User:
    id: str
    name: str
    color: str
    cursor_position: int = 0
    websocket: Optional[WebSocket] = None

@dataclass
class Session:
    id: str
    code: str = "# Welcome to SYNCOUT!\n# Start typing to collaborate...\n\nprint('Hello, World!')\n"
    language: str = "python"
    revision: int = 0
    users: Dict[str, User] = field(default_factory=dict)
    history: List[Operation] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

# ─────────────────────────────────────────────
# SESSION MANAGER
# ─────────────────────────────────────────────

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.user_colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
            "#FFEAA7", "#DDA0DD", "#98FB98", "#FFA07A",
            "#87CEEB", "#F0E68C"
        ]

    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())[:8].upper()
        session = Session(id=session_id)
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id.upper())

    def get_or_create_session(self, session_id: str) -> Session:
        session = self.get_session(session_id)
        if not session:
            session = Session(id=session_id.upper())
            self.sessions[session_id.upper()] = session
        return session

    def add_user(self, session: Session, name: str, websocket: WebSocket) -> User:
        user_id = str(uuid.uuid4())[:8]
        color = self.user_colors[len(session.users) % len(self.user_colors)]
        user = User(id=user_id, name=name, color=color, websocket=websocket)
        session.users[user_id] = user
        return user

    def remove_user(self, session: Session, user_id: str):
        if user_id in session.users:
            del session.users[user_id]

    def apply_operation(self, session: Session, op: Operation) -> bool:
        try:
            code = session.code

            if op.type == "insert":
                pos = min(op.position, len(code))
                session.code = code[:pos] + op.content + code[pos:]

            elif op.type == "delete":
                start = min(op.position, len(code))
                end = min(op.position + op.length, len(code))
                session.code = code[:start] + code[end:]

            elif op.type == "full_update":
                session.code = op.content

            session.revision += 1
            session.history.append(op)

            if len(session.history) > 100:
                session.history = session.history[-100:]

            return True
        except Exception as e:
            logger.error(f"Error applying operation: {e}")
            return False

    async def broadcast(self, session: Session, message: dict, exclude_user: str = None):
        disconnected = []
        for user_id, user in session.users.items():
            if user_id == exclude_user:
                continue
            if user.websocket:
                try:
                    await user.websocket.send_json(message)
                except Exception:
                    disconnected.append(user_id)

        for user_id in disconnected:
            self.remove_user(session, user_id)

    def get_users_info(self, session: Session) -> List[dict]:
        return [
            {
                "id": u.id,
                "name": u.name,
                "color": u.color,
                "cursor_position": u.cursor_position
            }
            for u in session.users.values()
        ]

manager = SessionManager()

# ─────────────────────────────────────────────
# REST ENDPOINTS
# ─────────────────────────────────────────────

@app.post("/api/sessions")
async def create_session():
    session = manager.create_session()
    return {
        "session_id": session.id,
        "created_at": session.created_at,
        "join_url": f"/session/{session.id}"
    }

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = manager.get_session(session_id)
    if not session:
        return {"error": "Session not found", "exists": False}
    return {
        "session_id": session.id,
        "language": session.language,
        "users_count": len(session.users),
        "revision": session.revision,
        "exists": True
    }

class ExecuteRequest(BaseModel):
    code: str
    language: str
    stdin: str = ""

@app.post("/api/execute")
async def execute_code(req: ExecuteRequest):
    result = await asyncio.to_thread(executor.execute, req.code, req.language, req.stdin)
    return result

@app.get("/api/stats")
async def get_stats():
    total_users = sum(len(s.users) for s in manager.sessions.values())
    return {
        "active_sessions": len(manager.sessions),
        "total_users": total_users,
        "uptime": "running"
    }

# ─────────────────────────────────────────────
# WEBSOCKET HANDLER
# ─────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = manager.get_or_create_session(session_id)
    user = None

    try:
        init_data = await websocket.receive_json()
        user_name = init_data.get("name", f"User{len(session.users) + 1}")
        user = manager.add_user(session, user_name, websocket)

        await websocket.send_json({
            "type": "init",
            "user_id": user.id,
            "user_name": user.name,
            "user_color": user.color,
            "code": session.code,
            "language": session.language,
            "revision": session.revision,
            "users": manager.get_users_info(session)
        })

        await manager.broadcast(session, {
            "type": "user_joined",
            "user": {
                "id": user.id,
                "name": user.name,
                "color": user.color,
                "cursor_position": 0
            },
            "users": manager.get_users_info(session)
        }, exclude_user=user.id)

        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            msg_type = data.get("type")

            if msg_type == "operation":
                op = Operation(
                    type=data.get("op_type", "full_update"),
                    position=data.get("position", 0),
                    content=data.get("content", ""),
                    length=data.get("length", 0),
                    user_id=user.id,
                    revision=data.get("revision", session.revision)
                )

                success = manager.apply_operation(session, op)

                if success:
                    await manager.broadcast(session, {
                        "type": "operation",
                        "op_type": op.type,
                        "position": op.position,
                        "content": op.content,
                        "length": op.length,
                        "user_id": user.id,
                        "user_name": user.name,
                        "user_color": user.color,
                        "revision": session.revision,
                        "code": session.code
                    }, exclude_user=user.id)

            elif msg_type == "cursor":
                user.cursor_position = data.get("position", 0)
                await manager.broadcast(session, {
                    "type": "cursor",
                    "user_id": user.id,
                    "user_name": user.name,
                    "user_color": user.color,
                    "position": user.cursor_position,
                    "line": data.get("line", 0),
                    "column": data.get("column", 0)
                }, exclude_user=user.id)

            elif msg_type == "language":
                session.language = data.get("language", "python")
                await manager.broadcast(session, {
                    "type": "language",
                    "language": session.language,
                    "user_id": user.id,
                    "user_name": user.name
                }, exclude_user=user.id)

            elif msg_type == "chat":
                await manager.broadcast(session, {
                    "type": "chat",
                    "user_id": user.id,
                    "user_name": user.name,
                    "user_color": user.color,
                    "message": data.get("message", ""),
                    "timestamp": time.time()
                })

            elif msg_type == "execute":
                exec_code = data.get("code", "")
                exec_lang = data.get("language", "python")
                exec_stdin = data.get("stdin", "")
                result = await asyncio.to_thread(executor.execute, exec_code, exec_lang, exec_stdin)
                exec_result = {
                    "type": "execution_result",
                    "user_id": user.id,
                    "user_name": user.name,
                    "user_color": user.color,
                    **result
                }
                # Send to executor
                await websocket.send_json(exec_result)
                # Broadcast to other collaborators
                await manager.broadcast(session, exec_result, exclude_user=user.id)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"User {user.name if user else 'Unknown'} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if user and session:
            manager.remove_user(session, user.id)
            await manager.broadcast(session, {
                "type": "user_left",
                "user_id": user.id,
                "user_name": user.name,
                "users": manager.get_users_info(session)
            })

# ─────────────────────────────────────────────
# FRONTEND STATIC
# ─────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app.mount(
    "/",
    StaticFiles(directory=os.path.join(BASE_DIR, "frontend"), html=True),
    name="frontend",
)
