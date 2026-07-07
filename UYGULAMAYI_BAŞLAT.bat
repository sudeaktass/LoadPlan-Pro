@echo off
:: Komut satırının senin klasöründen başlamasını sağlar
cd /d "%~dp0"

:: Streamlit uygulamasını çalıştırır
streamlit run app_3d.py

pause