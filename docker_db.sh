#!/bin/bash

# 프로젝트 루트에서 실행 확인
if [ ! -f "manage.py" ]; then
    echo "Error: 프로젝트 루트 디렉토리에서 실행하세요"
    exit 1
fi

# postgres-data 디렉토리 생성
mkdir -p postgres-data

docker run --name postgresql_db \
    -e POSTGRES_PASSWORD=DATABASSE_PSW \
    -p 5432:5432 \
    -v $(pwd)/postgres-data:/var/lib/postgresql/data \
    -d postgres:17.6
