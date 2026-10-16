# Optional: run agents inside a container so that tool calls cannot touch your machine.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git grep ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /rab
COPY . /rab
RUN pip install --no-cache-dir -r requirements.txt
ENTRYPOINT ["python", "-m", "rab"]
