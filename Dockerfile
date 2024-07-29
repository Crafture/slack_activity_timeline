# Use the official Python image from the Docker Hub
FROM python:3.10.4

# Set environment variables to ensure that the output is not buffered
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file to the container
COPY requirements.txt /app/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the container
COPY . /app/

# Expose the port on which the Flask app will run
EXPOSE 5000

# Define the command to run the Flask app
CMD ["python3", "app.py"]
