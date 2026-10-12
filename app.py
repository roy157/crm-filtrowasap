"""Punto de entrada.

Local:   python app.py            -> http://127.0.0.1:5000
Render:  gunicorn app:app --workers 1 --threads 8 --timeout 120
"""
import os

from crm import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"\n  CRM WhatsApp listo en  http://127.0.0.1:{port}")
    print(f"  Modo: {app.config['WA_MODE']}  ·  Simulador: http://127.0.0.1:{port}/simulador\n")
    # Sin reloader para no arrancar dos veces el programador de seguimientos
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False, threaded=True)
