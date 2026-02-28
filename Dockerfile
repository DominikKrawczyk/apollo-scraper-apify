FROM apify/actor-python-selenium:3.11
COPY . ./
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "__main__.py"]
