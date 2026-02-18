"""
SYNCOUT - Run Script
Usage: python run.py
"""
import uvicorn
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════╗
║          SYNCOUT - Pair Programmer         ║
║     Real-time Collaborative Code Editor   ║
╠═══════════════════════════════════════════╣
║  🌐 Open: http://localhost:8001           ║
║  📖 Docs: http://localhost:8001/docs      ║
║  🔄 WebSocket: ws://localhost:8001/ws/    ║
╚═══════════════════════════════════════════╝
    """)

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )
