ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV MUSIC_TAG_HOST=0.0.0.0
ENV MUSIC_TAG_PORT=6902

EXPOSE 6902

CMD ["python", "app.py"]
