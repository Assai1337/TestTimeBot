FROM python:3.11-slim AS base

WORKDIR /usr/src/app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

FROM base AS bot

CMD ["python", "bot.py"]

FROM nase AS web

CMD ["flash", "run", "--host=0.0.0.0", "--port=5000"]
