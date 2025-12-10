#!/bin/bash

# ===============================
# Configurações
# ===============================
APP_NAME="flask_app"
USER="rasp"
APP_PATH="/home/rasp/projeto/backend.py"
WORKING_DIR="/home/rasp/projeto"
PYTHON_PATH=$(which python3)
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# ===============================
# Criação do arquivo de serviço
# ===============================
echo "Criando arquivo de serviço systemd..."

sudo bash -c "cat > $SERVICE_FILE <<EOL
[Unit]
Description=Flask App Principal
After=network.target

[Service]
User=$USER
WorkingDirectory=$WORKING_DIR
ExecStart=$PYTHON_PATH $APP_PATH
Restart=always

[Install]
WantedBy=multi-user.target
EOL"

# ===============================
# Recarregar systemd e habilitar serviço
# ===============================
echo "Recarregando systemd e habilitando o serviço..."
sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME.service

# ===============================
# Iniciar serviço
# ===============================
echo "Iniciando serviço..."
sudo systemctl start $APP_NAME.service

# ===============================
# Status do serviço
# ===============================
sudo systemctl status $APP_NAME.service --no-pager

