@echo off
:: Claude Code'un tarayıcı panelinde uygulamayı açmak için kullanılır.
:: UYGULAMAYI_BAŞLAT.bat ile aynı işi yapar, tek farkı: tarayıcıyı kendisi
:: açmaz (headless) ve portu sabitler, sonunda "pause" yoktur.
:: Çalışma klasörünü bu dosyanın bulunduğu klasöre alır — veritabanı yolu
:: (./data/app.db) buna bağlı.
cd /d "%~dp0"
streamlit run app_3d.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
