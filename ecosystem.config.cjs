// pm2 config — corre FastAPI + Streamlit con el venv del python_agent.
// El mcp_server NO se levanta aquí: el agente lo lanza como subprocess
// vía stdio cuando recibe una pregunta (necesita estar compilado en dist/).
module.exports = {
  apps: [
    {
      name: "agent-api",
      cwd: "./python_agent",
      script: ".venv/bin/uvicorn",
      args: "server:app --host 0.0.0.0 --port 8001",
      interpreter: "none",
      env: { PYTHONUNBUFFERED: "1" },
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 30000,
    },
    {
      name: "agent-ui",
      cwd: "./python_agent",
      script: ".venv/bin/streamlit",
      args: "run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true",
      interpreter: "none",
      env: { PYTHONUNBUFFERED: "1" },
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 10000,
    },
  ],
};
