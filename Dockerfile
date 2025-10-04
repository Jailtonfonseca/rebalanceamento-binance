# --- Stage 1: Builder ---
# This stage installs dependencies into a virtual environment.
FROM python:3.12-slim as builder

# Set up a non-root user
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /home/appuser

# Create a virtual environment
RUN python -m venv /home/appuser/venv
ENV PATH="/home/appuser/venv/bin:$PATH"

# Copy and install requirements
COPY --chown=appuser:appuser requirements*.txt .
RUN pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Final Application Image ---
# This stage copies the installed dependencies and source code to a clean base image.
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DATA_DIR /data

# Set up a non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Copy the virtual environment from the builder stage
# The venv is copied to the user's home, not the workdir, to keep it separate.
COPY --from=builder /home/appuser/venv /home/appuser/venv

# Set the working directory to be the application's source root
WORKDIR /home/appuser/src

# Copy the application source code into the working directory
# The dot '.' means the contents of 'src' go into the current WORKDIR.
COPY --chown=appuser:appuser src .

# Make the venv activate
ENV PATH="/home/appuser/venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8080

# The command to run the application from within the src directory
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
