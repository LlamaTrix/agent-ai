#!/usr/bin/env bash
# Instalación inicial en el VPS. Ejecutar desde la raíz del repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "==> Repo root: $ROOT"

# 1) Python venv + deps
echo "==> Creando venv de Python en python_agent/.venv"
cd "$ROOT/python_agent"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 2) MCP Node: instalar deps y compilar a dist/
echo "==> Instalando deps y compilando mcp_server"
cd "$ROOT/mcp_server"
npm ci
npm run build
test -f dist/main.js || { echo "ERROR: dist/main.js no se generó"; exit 1; }

# 3) .env
echo "==> Verificando .env"
cd "$ROOT"
[ -f python_agent/.env ] || { cp python_agent/.env.example python_agent/.env; echo "    Creado python_agent/.env (EDITALO)"; }
[ -f mcp_server/.env ]   || { cp mcp_server/.env.example   mcp_server/.env;   echo "    Creado mcp_server/.env (EDITALO)"; }

# 4) Ajustar NODE_MCP_ENTRY al path real del repo
sed -i "s|^NODE_MCP_ENTRY=.*|NODE_MCP_ENTRY=$ROOT/mcp_server/dist/main.js|" python_agent/.env
sed -i "s|^NODE_MCP_CWD=.*|NODE_MCP_CWD=$ROOT/mcp_server|" python_agent/.env

cat <<EOF

==> Instalación completada.

Próximos pasos:
  1. Editá python_agent/.env (API_BASE_URL, ALLOW_ORIGINS, modelo Ollama).
  2. Asegurate de tener Ollama corriendo:    ollama serve &  ;  ollama pull qwen2.5:3b
  3. Levantar con pm2:                       pm2 start ecosystem.config.cjs
  4. Persistir:                              pm2 save && pm2 startup

EOF
