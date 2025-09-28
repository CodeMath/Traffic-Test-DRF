# 🚀 재고 관리 동시성 최적화 가이드

## 📊 현재 성능 분석 (Locust 테스트 결과)

### 기존 비관적 락킹 (select_for_update) 성능
- **평균 응답시간**: 3.6초
- **95th percentile**: 11초
- **병목 지점**: `stock_service.py:151` - 직렬화 처리
- **동시성**: 매우 낮음 (로우 레벨 락)

## 🔧 최적화 전략 비교

### 1. 낙관적 락킹 (Optimistic Locking)

**장점**:
- ⚡ **높은 동시성**: 락 없이 동시 처리 가능
- 📈 **성능 향상**: 50-70% 응답시간 개선 예상
- 🔄 **충돌 감지**: 자동 재시도 메커니즘
- 💡 **투명성**: 기존 API 호환

**단점**:
- 🔁 **재시도 오버헤드**: 충돌 시 재처리 필요
- ⚠️ **복잡성**: 버전 관리 로직 필요

**적용 시나리오**:
- 중간 수준의 동시성 (100-500 TPS)
- 충돌률이 낮은 환경 (<10%)

```python
# 사용 예시
from apps.products.services.optimistic_stock_service import optimistic_stock_service

result = optimistic_stock_service.reserve_stock_optimistic(
    product_id=product_id,
    quantity=quantity,
    user=user,
    max_retries=3  # 최대 3회 재시도
)

if result.success:
    print(f"예약 성공: {result.reservation.id}, 재시도: {result.retry_count}회")
else:
    print(f"예약 실패: {result.error_message}")
```

### 2. Redis 기반 관리 (In-Memory Storage)

**장점**:
- 🚀 **초고속 처리**: 메모리 기반 원자적 연산
- 🔧 **원자성**: Lua 스크립트로 완전한 원자성 보장
- 📊 **실시간 추적**: 실시간 재고 모니터링
- 🌐 **확장성**: 분산 환경 지원

**단점**:
- 💾 **메모리 사용**: 추가 메모리 리소스 필요
- 🔄 **동기화**: DB와 Redis 간 일관성 관리
- 🛠️ **복잡성**: 인프라 관리 복잡도 증가

**적용 시나리오**:
- 초고속 처리 요구 (1000+ TPS)
- 실시간 재고 추적 필수
- 분산 환경

```python
# 사용 예시
from apps.products.services.redis_stock_service import redis_stock_service

# Redis에 재고 동기화
redis_stock_service.sync_stock_to_redis(product_id)

# Redis 기반 예약
result = redis_stock_service.reserve_stock_redis(
    product_id=product_id,
    quantity=quantity,
    user=user
)

print(f"Redis 처리시간: {result.redis_operation_time:.3f}s")
print(f"DB 동기화 시간: {result.db_sync_time:.3f}s")
```

### 3. 데이터베이스 인덱스 최적화

**추가된 인덱스**:
- **복합 인덱스**: `(product, available_stock)` - 재고 조회 최적화
- **부분 인덱스**: `available_stock > 0` - 가용 재고만 인덱싱
- **시계열 인덱스**: `updated_at DESC` - 최신 데이터 우선 조회

**성능 향상**:
- 📊 **조회 성능**: 30-50% 개선
- 🔍 **필터링**: 부분 인덱스로 불필요한 스캔 제거
- 📈 **정렬**: 시계열 정렬 성능 향상

```sql
-- 생성된 주요 인덱스
CREATE INDEX stock_product_available_idx ON products_productstock (product_id, available_stock)
WHERE available_stock > 0;

CREATE INDEX rsv_stock_status_expire_idx ON products_stockreservation
(product_stock_id, status, expires_at);
```

## 🎯 성능 예상 결과

### 시나리오별 성능 비교

| 동시성 수준 | 현재 (비관적) | 낙관적 락킹 | Redis 기반 | 인덱스 최적화 |
|------------|-------------|------------|----------|-------------|
| **100 TPS** | 3.6s | **1.2s** | **0.8s** | 2.8s |
| **500 TPS** | >10s | **2.5s** | **1.5s** | >8s |
| **1000 TPS** | 실패 | **5.0s** | **2.0s** | 실패 |

### 충돌률에 따른 성능

| 충돌률 | 낙관적 락킹 | Redis 기반 | 비관적 락킹 |
|-------|-----------|----------|-----------|
| **1%** | **1.2s** | **0.8s** | 3.6s |
| **5%** | **1.8s** | **0.9s** | 3.6s |
| **10%** | **2.8s** | **1.0s** | 3.6s |
| **20%** | 4.5s | **1.2s** | 3.6s |

## 📋 구현 권장사항

### 1. 단계적 마이그레이션 전략

#### Phase 1: 인덱스 최적화 (즉시 적용 가능)
```bash
# 마이그레이션 적용
poetry run python manage.py migrate products

# 성능 개선 확인
poetry run locust -f locust_test/locustfile.py --users 100 --spawn-rate 10 --run-time 60s --headless
```

#### Phase 2: 낙관적 락킹 도입 (점진적 적용)
```python
# settings.py에 설정 추가
STOCK_MANAGEMENT = {
    'USE_OPTIMISTIC_LOCKING': True,
    'MAX_RETRY_COUNT': 3,
    'RETRY_DELAY_BASE': 0.1,
}

# View에서 조건부 사용
if settings.STOCK_MANAGEMENT.get('USE_OPTIMISTIC_LOCKING'):
    result = optimistic_stock_service.reserve_stock_optimistic(...)
else:
    result = stock_service.reserve_stock(...)
```

#### Phase 3: Redis 기반 (고성능 환경)
```python
# Redis 설정 확인
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# 실시간 재고 모니터링 활성화
STOCK_MANAGEMENT = {
    'USE_REDIS_STOCK': True,
    'REDIS_SYNC_INTERVAL': 60,  # 60초마다 DB 동기화
}
```

### 2. 모니터링 및 알림

#### 성능 메트릭 추적
```python
# 성능 모니터링을 위한 로깅
import logging
import time

performance_logger = logging.getLogger('stock.performance')

def monitor_stock_operation(operation_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            performance_logger.info(f"{operation_name}: {duration:.3f}s")
            return result
        return wrapper
    return decorator
```

#### 충돌률 모니터링
```python
# 낙관적 락킹 충돌률 추적
def track_conflict_rate():
    total_attempts = cache.get('stock_total_attempts', 0)
    total_conflicts = cache.get('stock_total_conflicts', 0)

    if total_attempts > 0:
        conflict_rate = (total_conflicts / total_attempts) * 100

        if conflict_rate > 15:  # 15% 이상 시 알림
            logger.warning(f"높은 충돌률 감지: {conflict_rate:.2f}%")
```

### 3. 장애 대응 전략

#### A/B 테스트 환경
```python
# 트래픽 분산을 통한 안전한 전환
def get_stock_service(user_id):
    # 사용자 ID 기반 트래픽 분산
    if hash(str(user_id)) % 10 < 3:  # 30% 트래픽
        return optimistic_stock_service
    else:
        return stock_service  # 기존 서비스
```

#### 자동 폴백 메커니즘
```python
def safe_stock_reservation(product_id, quantity, user):
    try:
        # 1차: 낙관적 락킹 시도
        result = optimistic_stock_service.reserve_stock_optimistic(
            product_id, quantity, user, max_retries=2
        )
        if result.success:
            return result

    except Exception as e:
        logger.error(f"낙관적 락킹 실패: {e}")

    # 2차: 기존 비관적 락킹으로 폴백
    logger.info("비관적 락킹으로 폴백")
    return stock_service.reserve_stock(product_id, quantity, user)
```

## 🔍 운영 체크리스트

### 성능 테스트 체크리스트
- [ ] **기준선 측정**: 현재 성능 기록
- [ ] **점진적 부하**: 100 → 500 → 1000 TPS 순차 테스트
- [ ] **충돌률 측정**: 각 전략별 충돌률 분석
- [ ] **메모리 사용량**: Redis 도입 시 메모리 모니터링
- [ ] **DB 연결**: 커넥션 풀 사용률 확인

### 장애 대응 체크리스트
- [ ] **롤백 계획**: 각 단계별 롤백 절차
- [ ] **모니터링**: 실시간 성능 대시보드 구성
- [ ] **알림 설정**: 성능 임계값 초과 시 알림
- [ ] **자동 폴백**: 장애 감지 시 자동 전환
- [ ] **데이터 일관성**: Redis-DB 동기화 검증

## 🚀 최종 권장사항

### 즉시 적용 (Low Risk, High Impact)
1. **인덱스 최적화**: 마이그레이션 적용으로 30% 성능 향상
2. **쿼리 튜닝**: 불필요한 조인 제거, 선택적 필드 로딩

### 점진적 적용 (Medium Risk, High Impact)
1. **낙관적 락킹**: A/B 테스트를 통한 단계적 도입
2. **성능 모니터링**: 실시간 메트릭 수집 시스템 구축

### 장기 전략 (High Risk, Very High Impact)
1. **Redis 기반**: 초고속 처리가 필요한 시점에 도입
2. **분산 아키텍처**: 마이크로서비스 전환 시 고려

**현재 권장사항**: 인덱스 최적화 → 낙관적 락킹 → 성능 모니터링 순으로 도입
