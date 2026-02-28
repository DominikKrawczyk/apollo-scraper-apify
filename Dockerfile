# Use Apify's Python image with Chrome
FROM apify/actor-python-selenium:3.11

# Force update Chrome to latest stable (fixes ChromeDriver mismatch)
RUN apt-get update && \
    apt-get install -y --only-upgrade google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Copy all files
COPY . ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the actor
CMD ["python", "__main__.py"]
