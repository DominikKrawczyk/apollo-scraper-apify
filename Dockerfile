# Use Apify's Python image with Chrome
FROM apify/actor-python-selenium:3.11

# Install prerequisites, add Chrome repo, install latest Chrome
RUN apt-get update && \
    apt-get install -y wget gnupg && \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Copy all files
COPY . ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the actor
CMD ["python", "__main__.py"]
