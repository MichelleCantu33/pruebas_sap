FROM python:3.10-bullseye

ENV ACCEPT_EULA=Y
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    gnupg2 \
    curl \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    apt-transport-https \
    software-properties-common \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV FLASK_APP=app.py
ENV FLASK_ENV=production

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]