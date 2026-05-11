import streamlit as st
import pandas as pd
from SQL_Server_AI_Agent_AUV import Runner

st.title("SQL Server AI Agent")

user_question = st.text_input("Pregunta al agente:")

if st.button("Consultar"):
    if not user_question:
        st.warning("Por favor, ingresa una pregunta.")
    else:
        runner = Runner()
        result = runner.run(user_question)

        parts = []
        answer = result.get("answer") or "_Sin respuesta_"
        parts.append("**Respuesta del agente**\n\n" + answer)

        data = result.get("data") or {"rows": [], "row_count": 0}

        # ✅ row_count estable
        if isinstance(data, dict):
            parts.append(f"**Resultados**: {int(data.get('row_count', 0) or 0)} filas")

        # ✅ Botón Excel si existe
        if result.get("excel_bytes") and result.get("excel_name"):
            st.download_button(
                "Descargar Excel completo",
                data=result["excel_bytes"],
                file_name=result["excel_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.markdown("\n\n".join(parts))

        # Mostrar tabla solo si el usuario la pidió explícitamente
        _TABLE_WORDS = ("tabla", "lista", "muestra", "dame", "todos", "todas", "listar", "ver", "detalle", "excel")
        show_table = any(w in user_question.lower() for w in _TABLE_WORDS)

        rows = data.get("rows") if isinstance(data, dict) else None
        if show_table and isinstance(rows, list) and rows:
            try:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
            except Exception:
                st.json(rows)
