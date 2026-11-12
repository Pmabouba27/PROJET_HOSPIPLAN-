# Contexte de build = racine du dépôt :
#   docker build -f service-identite/Dockerfile -t hospiplan-identite .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY libs/hospiplan_auth /libs/hospiplan_auth
COPY service-identite/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt /libs/hospiplan_auth

COPY service-identite/ .
RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8001
CMD ["gunicorn", "identite.wsgi", "--bind=0.0.0.0:8001", "--workers=2", "--access-logfile=-"]
