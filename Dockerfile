# Use Python 3.13 slim base
FROM python:3.13-slim

# Set working directory
WORKDIR /usr/src/app

# Copy requirements first for Docker cache
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN python3 -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy all bot code
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Start the bot
CMD ["bash", "start.sh"]
