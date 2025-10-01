FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry 설치 및 설정
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false

# 의존성 파일 복사 및 설치
COPY pyproject.toml poetry.lock /app/
RUN poetry install --no-root --no-interaction --no-ansi

# Entrypoint 스크립트 먼저 복사 및 실행 권한 부여
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 애플리케이션 코드 복사
COPY . /app

# 로그 디렉토리 생성
RUN mkdir -p /app/logs

# 포트 노출
EXPOSE 8882

# Entrypoint 스크립트 실행
ENTRYPOINT ["/app/entrypoint.sh"]
