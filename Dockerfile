FROM python:3.13-slim

WORKDIR /usr/src/app

# Install system packages needed to build some Python C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    python3-dev \
    autoconf \
    automake \
    make \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN python3 -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Make start.sh executable
RUN chmod +x start.sh

# Start the bot
CMD ["bash", "start.sh"]
