# api.py
from __future__ import annotations

import os
import base64
import asyncio
from typing import Optional, Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from SQL_Server_AI_Agent_AUV import ask_with_embedded_mcp  # ✅ usar directo

# -----------------------------
# CORS
# -----------------------------
ALLOW_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOW_ORIGINS",
        "http://localhost:3000"
    ).split(",") if o.strip()
]

app = FastAPI(title="AUVAGENT API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Models
# -----------------------------
class Question(BaseModel):
    query: str = Field(..., min_length=1)

class RowsPayload(BaseModel):
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    raw: Optional[Any] = None

class AskResponse(BaseModel):
    explanation: str
    data: RowsPayload
    sql_executed: Optional[str] = None
    excel_name: Optional[str] = None
    excel_bytes: Optional[str] = None  # base64

# -----------------------------
# (Opcional) limitar concurrencia
# evita levantar demasiados procesos node a la vez
# -----------------------------
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))
_sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"service": "auvagent-backend", "status": "ok"}

@app.post("/askai", response_model=AskResponse)
async def ask_agent(question: Question):
    async with _sem:
        try:
            # ✅ Llamada ASYNC directa a tu agente
            result = await ask_with_embedded_mcp(question.query)

            explanation = (result.get("answer") or "").strip()

            # ✅ tu contrato estable (rows/row_count)
            data_payload = result.get("data") or {"rows": [], "row_count": 0}

            # Por seguridad: normaliza si algo vino raro
            if not isinstance(data_payload, dict):
                data_payload = {"rows": [], "row_count": 0, "raw": data_payload}

            if "rows" not in data_payload:
                data_payload["rows"] = []
            if "row_count" not in data_payload:
                data_payload["row_count"] = len(data_payload.get("rows") or [])

            sql_executed = result.get("sql_executed")  # probablemente None en tu agente MCP
            excel_name = result.get("excel_name")
            excel_bytes = result.get("excel_bytes")

            # ✅ Normaliza excel a base64 string
            excel_b64: Optional[str] = None
            if isinstance(excel_bytes, (bytes, bytearray)):
                excel_b64 = base64.b64encode(excel_bytes).decode("ascii")
            elif isinstance(excel_bytes, str):
                # si ya viene base64
                excel_b64 = excel_bytes

            return {
                "explanation": explanation,
                "data": data_payload,
                "sql_executed": sql_executed,
                "excel_name": excel_name,
                "excel_bytes": excel_b64,
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
