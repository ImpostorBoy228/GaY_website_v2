FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x manage.py

CMD ["gunicorn", "video_platform.wsgi:application", "--bind", "0.0.0.0:8000"]