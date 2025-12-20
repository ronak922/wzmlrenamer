FROM python:3.13-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y curl \
 && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# ✅ Correct PATH for uv
ENV PATH="/root/.local/bin:$PATH"

RUN uv venv --system-site-packages

COPY requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
