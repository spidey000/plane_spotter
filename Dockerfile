# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables to ensure Python outputs everything to stdout/stderr
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's source code into the container
COPY . .

# Create a directory for logs if your application writes logs to a file
# and ensure the application has write permissions.
# If your application logs to stdout/stderr (common in containers), this might not be strictly necessary.
RUN mkdir -p /app/logs && chown -R nobody:nogroup /app/logs
# Assuming the application runs as a non-root user for better security.
# If your app needs to write to other specific directories, add them here.

# Expose a port if your application is a web service.
# For example, if your API runs on port 5000:
# EXPOSE 5000
# You will need to uncomment and adjust this if your application listens on a specific port.

# Command to run the application.
# This assumes 'main.py' is the entry point of your application.
# If your application is started differently (e.g., using gunicorn for a web app),
# you'll need to change this command.
CMD ["python", "main.py"]
