FROM python:3.9

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

VOLUME /srv

CMD ["python", "./telex2reddit.py"]
