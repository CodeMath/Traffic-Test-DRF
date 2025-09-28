# /bin/bash

docker run --name postgresql_db \
    -e POSTGRES_PASSWORD=DATABASSE_PSW \
    -p 5432:5432 \
    -v /Users/jaden/Documents/python_projects/Traffic-Test-DRF/postgres-data:/var/lib/postgresql/data \
    -d postgres:17.6
