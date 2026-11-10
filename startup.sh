#!/bin/bash
# Comando de inicialização do dashboard no Azure App Service (Linux, Python 3.11).
#
# O App Service expõe a porta em $PORT e faz health check em 0.0.0.0, por isso
# as duas flags abaixo. `--server.headless true` evita que o Streamlit tente
# abrir um navegador, e desligar o CORS/XSRF é necessário porque o App Service
# serve o app atrás do seu próprio proxy.
#
# Configure no App Service (Configuration → General settings → Startup Command):
#     bash startup.sh
set -euo pipefail

python -m streamlit run dashboard/app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
