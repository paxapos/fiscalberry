FROM python:3.11-slim

# Configurar variables de entorno
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Crear usuario no-root para seguridad
RUN groupadd -r devpanel && useradd -r -g devpanel devpanel

# Crear directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Crear directorio de logs
RUN mkdir -p logs && chown -R devpanel:devpanel /app

# Cambiar a usuario no-root
USER devpanel

# Exponer puerto
EXPOSE 8000

# Configurar variables de entorno por defecto
ENV DEVELOPER_PANEL_SECRET="change-this-secret-in-production"
ENV RABBITMQ_HOST="rabbitmq.restodigital.com.ar"
ENV RABBITMQ_PORT="5672"
ENV RABBITMQ_USER="fiscalberry"
ENV RABBITMQ_PASSWORD="fiscalberry123"
ENV RABBITMQ_VHOST="/"

# Comando de inicio
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]