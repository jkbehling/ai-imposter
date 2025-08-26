# Use official Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY . /app/

# Create a non-root user
RUN useradd --create-home django
RUN chown -R django:django /app
USER django

# Collect static files (optional, if you use Django staticfiles)
RUN python manage.py collectstatic --noinput

# Expose port (Daphne default)
EXPOSE 8000

# Start Daphne ASGI server
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "project.asgi:application"]