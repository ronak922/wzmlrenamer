FROM python:3.13-slim

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

# Create virtual environment (optional)
RUN python -m venv venv
ENV PATH="/usr/src/app/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
