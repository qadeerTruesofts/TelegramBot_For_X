# --------- Use official Python 3.11 slim image ----------
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
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# --------- Copy project files ----------
COPY . /app

# --------- Upgrade pip and install Python packages ----------
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --------- Set environment variables for Chromium ----------
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER=/usr/bin/chromedriver

# --------- Expose port (optional) ----------
EXPOSE 8080

# --------- Default command ----------
CMD ["python", "telegramBot_ForX.py"]
