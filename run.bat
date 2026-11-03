@echo off
cd /d "%~dp0"
python -m streamlit run app.py --server.address 127.0.0.1 --server.headless false --browser.gatherUsageStats false
pause
