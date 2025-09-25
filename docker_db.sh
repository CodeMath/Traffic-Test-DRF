# /bin/bash

docker run --name postgresql_db -e POSTGRES_PASSWORD=DATABASSE_PSW -p 5432:5432 -d postgres
