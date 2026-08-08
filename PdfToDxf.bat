@echo off
rem Abre o PdfToDxf com dois cliques, sem precisar de terminal.
rem Aceita um PDF arrastado sobre o icone: o arquivo ja abre carregado.

cd /d "%~dp0"

set "PYW=.venv\Scripts\pythonw.exe"

rem Nome unico por execucao: com um nome fixo, abrir a segunda janela enquanto a
rem primeira vive falha na hora, porque as duas disputam o mesmo arquivo.
set "ERRO=%TEMP%\pdftodxf-erro-%RANDOM%%RANDOM%.txt"

if not exist "%PYW%" (
    echo.
    echo Nao achei o ambiente virtual do projeto em:
    echo     %~dp0.venv
    echo.
    echo Crie com:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem pythonw nao abre janela preta atras do app. Como ele tambem engole as
rem mensagens de erro, o stderr vai para um arquivo e so aparece se algo falhar.
"%PYW%" main.py %* 2>"%ERRO%"
set CODIGO=%ERRORLEVEL%

if not "%CODIGO%"=="0" (
    echo.
    echo O PdfToDxf terminou com erro %CODIGO%:
    echo.
    if exist "%ERRO%" type "%ERRO%"
    echo.
    del "%ERRO%" >nul 2>&1
    pause
    exit /b %CODIGO%
)

del "%ERRO%" >nul 2>&1
exit /b 0
