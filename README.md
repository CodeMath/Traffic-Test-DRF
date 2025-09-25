# Traffic Django - 대용량 트래픽 테스트 Django App

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2+-green.svg)](https://djangoproject.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 대용량 트래픽 처리를 위한 Django 기반 재고 관리 시스템

## 🚀 프로젝트 개요

Traffic Django는 대용량 트래픽 환경에서 안정적인 재고 관리를 위해 설계된 고성능 DRF 애플리케이션입니다. 부하 테스트 및 성능 테스트 목적으로 공부를 위해 시작했습니다.

### ✨ 주요 특징

- **고성능 재고 관리**: Redis 캐싱과 PostgreSQL을 활용한 빠른 데이터 처리
- **실시간 예약 시스템**: 동시성 제어를 통한 안전한 재고 예약/해제
- **RESTful API**: DRF 기반의 완전한 API 문서화 (Swagger/OpenAPI)
- **성능 모니터링**: Silk 프로파일링과 메트릭 수집
- **JWT 인증**: djangorestframework-simplejwt를 활용한 보안
- **포괄적 테스팅**: 단위/통합/E2E 테스트 커버리지

## 📊 시스템 아키텍처

### 데이터 모델

```mermaid
erDiagram
    Product ||--|| ProductStock : has
    ProductStock ||--o{ StockReservation : reserves
    ProductStock ||--o{ StockTransaction : records

    Product {
        uuid id PK
        string name
        text description
        decimal price
        string status
        datetime created_at
        datetime updated_at
    }

    ProductStock {
        uuid id PK
        uuid product_id FK
        int physical_stock
        int reserved_stock
        int available_stock
        int min_stock_level
        int reorder_point
        string warehouse_code
        datetime updated_at
    }

    StockReservation {
        uuid id PK
        uuid product_stock_id FK
        int quantity
        uuid user_id
        string order_id
        string status
        datetime expires_at
        datetime created_at
    }

    StockTransaction {
        uuid id PK
        uuid product_stock_id FK
        string transaction_type
        int quantity
        string reason
        uuid user_id
        datetime created_at
    }
```

### 핵심 비즈니스 로직

1. **재고 가용성 체크**: 실시간 재고 확인 및 예약 가능 수량 계산
2. **재고 예약 요청**: 동시성 제어를 통한 안전한 예약 처리
3. **재고 예약 확정**: 예약된 재고의 최종 확정 처리
4. **재고 예약 취소/해제**: 예약 취소 및 재고 복구
5. **재고 입고**: 물리적 재고 증가 및 트랜잭션 기록
6. **재고 트랜잭션**: 모든 재고 변동 내역 추적

## 🛠️ 기술 스택

### Backend
- **Framework**: Django 5.2+ / Django REST Framework 3.15+
- **Database**: PostgreSQL (psycopg2)
- **Cache**: Redis (django-redis)
- **Authentication**: JWT (djangorestframework-simplejwt)
- **Task Queue**: Celery 5.5+

### Development & Testing
- **Code Quality**: Ruff (formatting & linting)
- **Testing**: pytest-django, factory-boy, faker
- **Performance**: django-silk, locust
- **API Documentation**: drf-spectacular (OpenAPI/Swagger)

### Infrastructure
- **Environment**: django-environ
- **Logging**: python-json-logger
- **Monitoring**: psutil
- **Development**: django-extensions, ipython

## 📋 요구사항

- Python 3.13+
- PostgreSQL 12+
- Redis 6+
- Poetry (의존성 관리)

## 🚦 설치 및 설정

### 1. 저장소 클론

```bash
git clone https://github.com/your-username/traffic_django.git
cd traffic_django
```

### 2. Poetry 설치 및 의존성 설치

```bash
# Poetry 설치 (없는 경우)
curl -sSL https://install.python-poetry.org | python3 -

# 의존성 설치
poetry install

# 개발 의존성 포함 설치
poetry install --with dev
```

### 3. 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# 환경변수 설정 (예시)
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgresql://user:password@localhost:5432/traffic_django
REDIS_URL=redis://localhost:6379/0
```

### 4. 데이터베이스 설정

```bash
# 활성화
poetry shell

# 마이그레이션
python manage.py migrate

# 슈퍼유저 생성
python manage.py createsuperuser
```

### 5. 개발 서버 실행

```bash
# Django 개발 서버
python manage.py runserver

# Celery Worker (별도 터미널)
celery -A config worker -l info

# Redis 서버 (별도 터미널)
redis-server
```

## 🔌 API 엔드포인트

### 인증
- `POST /api/token/` - JWT 토큰 발급
- `POST /api/token/refresh/` - JWT 토큰 갱신

### 상품 관리
- `GET /api/products/` - 상품 목록 조회
- `POST /api/products/` - 상품 생성
- `GET /api/products/{id}/` - 상품 상세 조회
- `PUT /api/products/{id}/` - 상품 수정
- `DELETE /api/products/{id}/` - 상품 삭제

### 재고 관리
- `GET /api/products/stock/available/` - 가용 재고 조회
- `POST /api/products/stock/inbound/` - 재고 입고 (관리자만)
- `POST /api/products/stock/reserve/` - 재고 예약

### API 문서
- `GET /api/schema/swagger-ui/` - Swagger UI
- `GET /api/schema/redoc/` - ReDoc
- `GET /api/schema/` - OpenAPI 스키마

## 🧪 테스트 실행

```bash
# 전체 테스트 실행
poetry run pytest

# 커버리지 포함
poetry run pytest --cov=apps

# 특정 앱 테스트
poetry run pytest apps/products/tests/

# 성능 테스트
poetry run pytest apps/products/tests/performance/

# E2E 테스트
poetry run pytest apps/products/tests/e2e/
```

## 📊 성능 모니터링

### Django Silk 프로파일링
```bash
# Silk 활성화 (DEBUG=True 시 자동)
python manage.py runserver

# 접속: http://localhost:8000/silk/
```

### Locust 부하 테스트
```bash
# Locust 실행
poetry run locust -f locustfile.py --host=http://localhost:8000

# 접속: http://localhost:8089/
```

## 📁 프로젝트 구조

```
traffic_django/
├── apps/
│   └── products/           # 상품/재고 관리 앱
│       ├── models.py       # 데이터 모델
│       ├── serializers/    # DRF 시리얼라이저
│       ├── views.py        # API 뷰
│       ├── services/       # 비즈니스 로직 서비스
│       ├── filters.py      # 필터링 로직
│       └── tests/          # 테스트 코드
├── config/                 # Django 설정
│   ├── settings/           # 환경별 설정
│   ├── urls.py            # URL 설정
│   └── wsgi.py            # WSGI 설정
├── logs/                  # 로그 파일
├── staticfiles/           # 정적 파일
└── manage.py              # Django 관리 명령
```

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
