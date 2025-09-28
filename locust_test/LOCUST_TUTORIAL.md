# Locust 부하 테스트 가이드

## 🎯 개요

이 문서는 Traffic Django 재고 관리 시스템의 대용량 트래픽 부하 테스트를 위한 Locust 설정 및 실행 가이드입니다.

## 📋 테스트 시나리오

### 테스트 대상 사용자
- **총 사용자**: 10,000명
- **계정명**: `user{i}` (i는 0부터 9999까지)
- **비밀번호**: 모든 계정 공통으로 `password`

### 테스트 워크플로우
1. **JWT 인증**: 사용자별 액세스 토큰 획득
2. **상품 조회**: `/api/products/` 엔드포인트에서 상품 목록 조회
3. **재고 가용성 체크**: `/api/products/stock/available/?product_id={id}` 엔드포인트로 재고 확인
4. **재고 예약**: `/api/products/stock/reserve/` 엔드포인트로 재고 예약 (수량: 1-100개 랜덤)

## 🏗️ Locust 테스트 구조

### 사용자 클래스 구조
```python
class StockTestUser(FastHttpUser):
    """재고 관리 시스템 부하 테스트용 사용자 클래스"""

    wait_time = between(1, 3)  # 요청 간 대기 시간

    def on_start(self):
        """사용자 초기화 및 인증"""

    @task(weight=3)
    def test_product_list(self):
        """상품 목록 조회 테스트"""

    @task(weight=2)
    def test_stock_availability(self):
        """재고 가용성 체크 테스트"""

    @task(weight=1)
    def test_stock_reservation(self):
        """재고 예약 테스트"""
```

### 핵심 구현 요소

#### 1. 사용자 인증 시스템
- 10,000개 계정 중 랜덤 선택
- JWT 토큰 획득 및 헤더 설정
- 토큰 만료 시 자동 갱신

#### 2. 상품 조회 및 선택
- 페이지네이션 처리
- 랜덤 상품 선택
- 상품 ID 캐싱

#### 3. 재고 가용성 체크
- 선택된 상품의 재고 상태 확인
- 가용 재고량 검증
- 예약 가능 여부 판단

#### 4. 재고 예약 처리
- 1-100개 사이 랜덤 수량 생성
- 동시성 제어 테스트
- 예약 성공/실패 메트릭 수집

## 🔧 환경 설정

### 필수 조건
```bash
# Django 개발 서버 실행
poetry shell
python manage.py runserver 0.0.0.0:8000

# Redis 서버 실행 (별도 터미널)
redis-server

# PostgreSQL 서버 실행
brew services start postgresql
```

### 테스트 데이터 준비
```python
# Django shell에서 테스트 사용자 생성
python manage.py shell

from django.contrib.auth.models import User

# 10,000명 사용자 생성
users = []
for i in range(10000):
    user = User(username=f'user{i}')
    user.set_password('password')
    users.append(user)

User.objects.bulk_create(users, batch_size=1000)
print(f"Created {User.objects.count()} users")
```

## 🚀 테스트 실행

### 기본 실행
```bash
# Locust 웹 인터페이스로 실행
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000

# 브라우저에서 접속: http://localhost:8089
```

### 고급 실행 옵션
```bash
# 헤드리스 모드로 실행 (GUI 없음)
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 10 --run-time 300s --headless

# CSV 결과 저장
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 10 --run-time 300s --headless \
  --csv=results/load_test
```

### 단계별 부하 증가 테스트
```bash
# 단계적으로 사용자 수 증가
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 100 --spawn-rate 5 --run-time 60s --headless --csv=results/test_100

poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 500 --spawn-rate 25 --run-time 60s --headless --csv=results/test_500

poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 50 --run-time 60s --headless --csv=results/test_1000
```

## 📊 성능 메트릭 모니터링

### 주요 모니터링 지표
- **응답 시간**: 평균/중간값/95백분위수
- **처리량**: 초당 요청 수 (RPS)
- **에러율**: 실패한 요청 비율
- **동시 사용자 수**: 실제 동시 접속자 수

### Django Silk 프로파일링 연동
```python
# 프로파일링 활성화
DEBUG = True  # config/base.py

# Silk 대시보드 접속
http://localhost:8000/silk/
```

### 시스템 리소스 모니터링
```bash
# CPU/메모리 사용량 모니터링
htop

# 데이터베이스 연결 상태 확인
python manage.py dbshell
\l  -- 데이터베이스 목록
\dt -- 테이블 목록
```

## 🎛️ 부하 테스트 시나리오

### 1. 기본 성능 테스트 (Baseline)
- **사용자**: 100명
- **지속 시간**: 5분
- **목표**: 기본 성능 지표 수집

### 2. 중간 부하 테스트 (Moderate Load)
- **사용자**: 500명
- **지속 시간**: 10분
- **목표**: 일반적인 트래픽 상황 테스트

### 3. 고부하 테스트 (High Load)
- **사용자**: 1,000명
- **지속 시간**: 15분
- **목표**: 시스템 한계점 탐지

### 4. 스트레스 테스트 (Stress Test)
- **사용자**: 2,000-5,000명
- **지속 시간**: 20분
- **목표**: 시스템 파괴점 및 복구 능력 테스트

## 🔍 결과 분석

### 성공 기준
- **응답 시간**: 95%의 요청이 2초 이내 완료
- **에러율**: 1% 미만
- **처리량**: 분당 1,000건 이상 처리
- **재고 정합성**: 재고 부족 시 적절한 에러 응답

### 병목 지점 식별
1. **데이터베이스 쿼리**: N+1 문제, 인덱스 최적화
2. **JWT 인증**: 토큰 검증 성능
3. **Redis 캐싱**: 캐시 히트율 최적화
4. **동시성 제어**: 재고 예약 시 락 경합

## ⚠️ 주의사항

### 테스트 환경 설정
- 프로덕션과 유사한 환경에서 테스트
- 충분한 테스트 데이터 준비
- 네트워크 지연시간 고려

### 시스템 보호
- 테스트 전 데이터베이스 백업
- 테스트용 격리된 환경 사용
- 실제 서비스에 영향 없도록 주의

### 모니터링
- 시스템 리소스 지속 모니터링
- 로그 파일 용량 증가 주의
- 테스트 중 장애 발생 시 즉시 중단

## 🚀 고급 최적화 팁

### 1. 연결 풀 최적화
```python
# config/base.py
DATABASES = {
    'default': {
        # ...
        'OPTIONS': {
            'MAX_CONNS': 20,
            'MIN_CONNS': 5,
        }
    }
}
```

### 2. Redis 캐싱 전략
```python
# 재고 정보 캐싱
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'MAX_CONNECTIONS': 50,
        }
    }
}
```

### 3. 비동기 처리
```python
# Celery를 활용한 비동기 작업
@shared_task
def process_stock_reservation(reservation_id):
    # 재고 예약 후처리 로직
    pass
```

이 가이드를 통해 체계적이고 효과적인 부하 테스트를 수행하여 시스템의 성능과 안정성을 검증할 수 있습니다.
