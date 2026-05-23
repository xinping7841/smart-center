ARG BASE_IMAGE=mcr.microsoft.com/devcontainers/python:1-3.11-bullseye
FROM ${BASE_IMAGE}

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/meter_service

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

USER root

EXPOSE 6901

CMD ["python", "-m", "meter_service.app"]
