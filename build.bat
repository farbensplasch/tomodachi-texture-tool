@echo off
echo Installing build dependencies...
pip install pyinstaller
echo.
echo Building...
pyinstaller TomodachiTextureTool.spec
echo.
echo Done! Executable is at: dist\TomodachiTextureTool.exe
pause
