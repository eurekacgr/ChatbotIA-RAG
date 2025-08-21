import base64
import mimetypes
from pathlib import Path
import gradio as gr
import os
from rag_chain import answer, GOODBYE_RE
from analysis_interface import create_analysis_tab
from auth_layer import AuthManager

ORG = "#284293"  # azul CGR
SUGERENCIA_HTML = (
    "Sugerencia: Puedes pedir "
    "Dame las sanciones por no presentación de declaraciones "
    "Dame las razones de sanción más frecuentes"
)

CSS = f"""
:root {{ --prim:{ORG}; }}
body, .gradio-container {{ background:white; font-family:'Poppins',sans-serif; }}
#wrap {{ max-width:680px; margin: 24px auto 40px; }}
#logo img {{ height:96px; display:block; margin:0 auto; }}
#title {{ color:var(--prim); text-align:center; font-weight:600; margin:16px 0 8px; }}
#chatbot, #chatbot * {{ background:#f2f4ff !important; color:#284293 !important; border:none !important; }}
#chatbot .label {{ display:none !important; }}
#inbox textarea {{ background:var(--prim)!important; color:white!important; font-weight:600; text-align:center; border:none; border-radius:10px; }}
#inbox .gr-button {{ display:none; }} /* ocultar botón: solo Enter */
#note {{ font-size:12px; text-align:center; color:#ffa76c; margin-top:10px; font-weight: bold;}}

/* Estilos para análisis de documentos */
.analysis-container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.status-box {{ padding: 10px; border-radius: 5px; margin: 10px 0; }}
.success {{ background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; }}
.error {{ background-color: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }}
.summary-box {{ border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin: 10px 0; }}
.summary-textbox textarea {{ 
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
    line-height: 1.5 !important;
}}
.precedents-container {{
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 20px;
    margin: 10px 0;
}}
.precedents-container h3 {{
    color: #284293;
    margin-top: 0;
    margin-bottom: 15px;
    font-size: 18px;
    font-weight: bold;
}}
.precedents-container h4 {{
    color: #495057;
    margin-top: 15px;
    margin-bottom: 10px;
    font-size: 16px;
    font-weight: bold;
}}
.precedent-item {{
    background-color: white;
    border: 1px solid #e9ecef;
    border-radius: 5px;
    padding: 15px;
    margin: 10px 0;
}}
.score {{
    background-color: #007bff;
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: bold;
}}
.precedents-container hr {{
    border: none;
    height: 1px;
    background-color: #dee2e6;
    margin: 15px 0;
}}

/* Estilos para autenticación */
#auth_code {{ max-width: 300px; margin: 0 auto; }}
"""

# Inicializar el gestor de autenticación
auth_manager = AuthManager()

def chat_fn(msg, hist, user_code):
    # Verificar permisos antes de procesar
    can_query, permission_msg = auth_manager.check_query_permission(user_code)
    if not can_query:
        if not hist:
            hist = []
        hist.append((msg, f"❌ {permission_msg}"))
        yield "", hist
        return
    
    if not hist:
        hist = [("", "¡Hola! 👋 Soy **Lexi** de la División Jurídica.\nIndíqueme por ejemplo cuáles resoluciones hay contra Carlos Francisco Soto. También puedo conversar en general.")]
        yield "", hist
    
    hist.append((msg, "⌛ Consultando…")); yield "", hist
    
    try:
        # Registrar la consulta antes de procesarla
        auth_manager.record_query(user_code)
        resp, _ = answer(msg, k=10)
    except Exception as e:
        print(f"Error en chat_fn: {e}")
        resp = "⚠️ Ocurrió un error procesando su consulta. Por favor, intente de nuevo."
    
    hist[-1] = (msg, resp); yield "", hist

# Obtener variables de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

with gr.Blocks(css=CSS, title="RAG | Resoluciones DJ") as demo:
    # Estado para almacenar el código de usuario autenticado
    user_code_state = gr.State(value=None)
    
    # Interfaz de autenticación
    auth_column, code_input, auth_btn, auth_status = auth_manager.create_auth_interface()
    
    # Contenido principal (inicialmente oculto)
    with gr.Column(visible=False) as main_content:
        with gr.Tabs():
            # Pestaña original del RAG
            with gr.TabItem("💬 Consulta RAG"):
                with gr.Column(elem_id="wrap"):
                    gr.Markdown("<h1 id='title'>RAG&nbsp; |&nbsp; Resoluciones de acto final (DJ)</h1>")
                    chat = gr.Chatbot(type="tuples", elem_id="chatbot")
                    with gr.Row(elem_id="inbox"):
                        txt = gr.Textbox(placeholder="Escriba su consulta… (p. ej., cuáles resoluciones hay contra Carlos Francisco Soto)", show_label=False, lines=1, container=False)
                    gr.HTML(f"<div id='note'>{SUGERENCIA_HTML}</div>")
                    txt.submit(chat_fn, [txt, chat, user_code_state], [txt, chat])
            
            # Nueva pestaña de análisis de documentos
            with gr.TabItem("📄 Análisis de Documento"):
                if GEMINI_API_KEY and QDRANT_URL and QDRANT_API_KEY:
                    analysis_interface = create_analysis_tab(GEMINI_API_KEY, QDRANT_URL, QDRANT_API_KEY)
                else:
                    gr.Markdown("""
                    ## ⚠️ Configuración incompleta
                    
                    Para usar el análisis de documentos, asegúrese de que las siguientes variables de entorno estén configuradas:
                    - `GEMINI_API_KEY`
                    - `QDRANT_URL` 
                    - `QDRANT_API_KEY`
                    """)
    
    # Configurar la autenticación
    auth_btn.click(
        fn=auth_manager.authenticate,
        inputs=[code_input],
        outputs=[auth_column, main_content, auth_status, user_code_state]
    )
    
    # También permitir autenticación con Enter
    code_input.submit(
        fn=auth_manager.authenticate,
        inputs=[code_input],
        outputs=[auth_column, main_content, auth_status, user_code_state]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", pwa=True, server_port=int(os.environ.get('PORT', 8080)))
