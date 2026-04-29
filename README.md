# ai-prueba — Agente SQL + MCP

Monorepo con dos componentes:

- **python_agent/** — Agente Python (FastAPI + Streamlit) que orquesta un LLM y consume tools del MCP.
- **mcp_server/** — Servidor MCP en TypeScript que expone tools HTTP contra una API Laravel.

El agente Python **lanza el MCP como subprocess vía stdio** (no es un servicio HTTP). Por eso pm2 sólo administra los procesos Python; el MCP sólo necesita estar compilado en `mcp_server/dist/`.

## Requisitos en el VPS

- Python 3.10+ con `python3-venv`
- Node.js 18+ y `npm`
- `pm2` global: `npm i -g pm2`
- Ollama con el modelo deseado: `ollama pull qwen2.5:3b`

## Instalación

```bash
git clone <tu-repo> ai-prueba
cd ai-prueba
chmod +x install.sh
./install.sh
```

El script crea el venv, instala dependencias Python y Node, compila el MCP a `dist/`, y genera los `.env` desde los `.env.example` ajustando los paths absolutos automáticamente.

Después editá `python_agent/.env`:
- `API_BASE_URL` → URL real de tu API Laravel
- `ALLOW_ORIGINS` → dominios del frontend
- `LLAMA_MODEL` → modelo de Ollama (default `qwen2.5:3b`)

## Ejecución con pm2

```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup    # seguir las instrucciones que imprime
```

Procesos:
- `agent-api` → FastAPI en `:8001` (endpoint `POST /askai`)
- `agent-ui`  → Streamlit en `:8501`

Comandos útiles:
```bash
pm2 ls
pm2 logs agent-api
pm2 logs agent-ui
pm2 restart agent-api
```

## Nginx (ejemplo)

```nginx
server {
  server_name api.tudominio.com;
  location / {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}

server {
  server_name app.tudominio.com;
  location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
  }
}
```

Luego `certbot --nginx -d api.tudominio.com -d app.tudominio.com`.

## Actualizar tras un `git pull`

```bash
cd ai-prueba
git pull
# si cambió requirements.txt:
python_agent/.venv/bin/pip install -r python_agent/requirements.txt
# si cambió mcp_server:
(cd mcp_server && npm ci && npm run build)
pm2 restart all
```

## Estructura

```
ai-prueba/
├── ecosystem.config.cjs       # config pm2
├── install.sh                 # script de bootstrap
├── python_agent/
│   ├── .env.example
│   ├── requirements.txt
│   ├── server.py              # FastAPI (uvicorn)
│   ├── app.py                 # Streamlit UI
│   ├── main.py                # (legacy, no se usa con pm2)
│   ├── SQL_Server_AI_Agent_AUV.py
│   └── exports/               # excel generado en runtime
└── mcp_server/
    ├── .env.example
    ├── package.json
    ├── tsconfig.json
    └── main.ts                # se compila a dist/main.js
```
