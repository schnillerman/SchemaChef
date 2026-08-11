FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY translations ./translations
COPY templates ./templates
# .po -> .mo bei jedem Build - .mo-Binaerdateien werden bewusst NICHT
# committet, damit Weblate-Contributions (nur .po) direkt nutzbar
# bleiben, ohne Merge-Konflikte auf Binaerdateien.
RUN pybabel compile -d translations

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

# 2 Worker: reicht fuer Single-User-Betrieb. Timeout grosszuegig, da
# /extract bis zu zwei sequenzielle LLM-Calls macht (Extraktion +
# Anreicherung) - bei einer langsamen Modellantwort oder langsamer
# Quellseite kann das die alten 90s ueberschreiten.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "180", "app.main:app"]
