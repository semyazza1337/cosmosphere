FROM python:3.11-slim

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml ./
COPY cosmosphere/ ./cosmosphere/
COPY prompts/ ./prompts/

RUN uv sync --no-dev

RUN mkdir -p data/digests data/explanations data/posts data/weekly

ADD https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic

COPY crontab /etc/cosmosphere-crontab

VOLUME ["/app/data"]

CMD ["supercronic", "/etc/cosmosphere-crontab"]
