# --------- Use official Python 3.11 image ----------
FROM python:3.11-slim

# --------- Set working directory ----------
WORKDIR /app

# --------- Install system dependencies ----------
RUN apt-get update && \
    apt-get install -y \
    chromium \
    chromium-driver \
    curl \
    wget \
    unzip \
    git \
    build-essential \
    libnss3 \
    libgconf-2-4 \
    libxi6 \
    libxcursor1 \
    libxcomposite1 \
    libasound2 \
    libxdamage1 \
    libxrandr2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# --------- Copy your project files ----------
COPY . /app

# --------- Upgrade pip and install Python packages ----------
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --------- Set environment variables for Chromium ----------
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/bin/chromium

# --------- Expose port (optional, not required for Telegram bot) ----------
EXPOSE 8080

# --------- Run the bot ----------
CMD ["python", "telegramBot_ForX.py"]
