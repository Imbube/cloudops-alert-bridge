@echo off
rem CloudOps Alert Bridge - inicia a API e abre a interface no navegador.
rem Uso: clique duas vezes neste arquivo. Para parar: feche esta janela ou Ctrl+C.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Primeira execucao: criando o ambiente virtual e instalando dependencias...
  python -m venv .venv || goto :erro
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :erro
)

if not exist ".env" (
  echo [AVISO] Arquivo .env nao encontrado. Copie .env.example para .env e preencha.
  echo         Sem ele a interface abre, mas nenhuma issue e criada no Jira.
)

rem Abre o navegador alguns segundos depois, quando a API ja estiver de pe.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/"

echo Iniciando a API em http://127.0.0.1:8000  (Ctrl+C para parar)
".venv\Scripts\python.exe" -m uvicorn app.main:app
pause
exit /b

:erro
echo.
echo Falha na instalacao. Verifique se o Python 3.10+ esta instalado e no PATH.
pause
