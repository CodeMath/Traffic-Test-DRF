# PostgreSQL 재고 시스템 최적화 가이드

## 격리 수준별 특성 분석

### 1. READ COMMITTED (기본값)
```sql
-- 현재 Django 기본 설정
SET default_transaction_isolation = 'read committed';
```

**특성:**
- ✅ 높은 동시성, 낮은 락킹 오버헤드
- ❌ Non-repeatable read 가능
- ❌ Phantom read 가능
- **적합한 시나리오**: 낮은 경합 상황, 빠른 응답 필요

### 2. REPEATABLE READ (권장)
```sql
-- 재고 트랜잭션용 권장 설정
SET default_transaction_isolation = 'repeatable read';
```

**특성:**
- ✅ 트랜잭션 내 일관된 읽기 보장
- ✅ Non-repeatable read 방지
- ❌ 여전히 phantom read 가능 (PostgreSQL에서는 대부분 방지됨)
- ⚖️ 적절한 성능과 일관성의 균형

### 3. SERIALIZABLE (고위험 상황용)
```sql
-- 높은 일관성이 필요한 경우
SET default_transaction_isolation = 'serializable';
```

**특성:**
- ✅ 완전한 격리 보장
- ❌ 높은 직렬화 오류율
- ❌ 성능 저하
- **적합한 시나리오**: 금융 거래, 결제 등 높은 정확성 필요

## PostgreSQL 설정 최적화

### postgresql.conf 권장 설정

```ini
# 동시성 관련 설정
max_connections = 200
shared_buffers = 4GB
effective_cache_size = 12GB

# 락킹 관련 설정
max_locks_per_transaction = 256
max_pred_locks_per_transaction = 256
max_pred_locks_per_relation = 256
max_pred_locks_per_page = 8

# 로깅 설정 (성능 모니터링용)
log_lock_waits = on
deadlock_timeout = 1s
log_statement = 'all'  # 개발 환경에서만
log_duration = on
log_min_duration_statement = 1000  # 1초 이상 쿼리 로깅

# 체크포인트 설정
checkpoint_completion_target = 0.9
wal_buffers = 64MB
```

### 연결 풀 설정

```python
# settings/production.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'OPTIONS': {
            'pool': True,
            'pool_size': 20,
            'max_overflow': 30,
            'pool_timeout': 30,
            'pool_recycle': 3600,
            # 격리 수준 설정
            'isolation_level': psycopg.IsolationLevel.REPEATABLE_READ,
            'options': '-c default_transaction_isolation=repeatable\ read'
        },
    }
}
```

## 인덱스 최적화

### 재고 관련 핵심 인덱스

```sql
-- 1. 동시성 최적화용 부분 인덱스
CREATE INDEX CONCURRENTLY idx_stock_available_gt_zero
ON products_productstock (product_id, available_stock)
WHERE available_stock > 0;

-- 2. 예약 만료 처리 최적화
CREATE INDEX CONCURRENTLY idx_reservation_expires_pending
ON products_stockreservation (expires_at, status)
WHERE status = 'pending';

-- 3. 트랜잭션 로그 성능 최적화
CREATE INDEX CONCURRENTLY idx_transaction_product_created
ON products_stocktransaction (product_stock_id, created_at DESC);

-- 4. 사용자별 예약 조회 최적화
CREATE INDEX CONCURRENTLY idx_reservation_user_status_created
ON products_stockreservation (user_id_id, status, created_at DESC);
```

### 통계 정보 업데이트

```sql
-- 정확한 쿼리 플래닝을 위한 통계 업데이트
ANALYZE products_productstock;
ANALYZE products_stockreservation;
ANALYZE products_stocktransaction;

-- 자동 통계 업데이트 설정
ALTER TABLE products_productstock SET (autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE products_stockreservation SET (autovacuum_analyze_scale_factor = 0.05);
```

## 모니터링 쿼리

### 1. 락 대기 모니터링

```sql
-- 현재 대기 중인 락 확인
SELECT
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS blocking_statement,
    blocked_activity.application_name AS blocked_application,
    blocking_activity.application_name AS blocking_application,
    blocked_locks.mode AS blocked_mode,
    blocking_locks.mode AS blocking_mode,
    blocked_locks.locktype AS blocked_locktype,
    blocking_locks.locktype AS blocking_locktype
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_activity blocked_activity
    ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_activity blocking_activity
    ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

### 2. 데드락 분석

```sql
-- 데드락 로그 분석 (로그에서)
SELECT
    extract(epoch from now() - query_start) AS duration,
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC;
```

### 3. 재고 테이블 성능 모니터링

```sql
-- 테이블별 락 통계
SELECT
    schemaname,
    tablename,
    n_tup_ins AS inserts,
    n_tup_upd AS updates,
    n_tup_del AS deletes,
    n_tup_hot_upd AS hot_updates,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch
FROM pg_stat_user_tables
WHERE tablename LIKE 'products_%stock%'
ORDER BY n_tup_upd DESC;
```

## 성능 벤치마킹

### 격리 수준별 TPS 비교

```python
# 테스트 스크립트 예시
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

def benchmark_isolation_levels():
    isolation_levels = [
        'READ COMMITTED',
        'REPEATABLE READ',
        'SERIALIZABLE'
    ]

    for level in isolation_levels:
        start_time = time.time()

        # 동시 예약 시뮬레이션
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for i in range(1000):
                future = executor.submit(
                    simulate_reservation,
                    isolation_level=level
                )
                futures.append(future)

            # 결과 수집
            results = [f.result() for f in futures]

        duration = time.time() - start_time
        success_rate = sum(1 for r in results if r['success']) / len(results)

        print(f"{level}: {len(results)/duration:.2f} TPS, "
              f"성공률: {success_rate:.2%}")
```

## 권장 운영 전략

### 1. 단계적 적용

```python
# Phase 1: 기본 개선
ISOLATION_LEVEL = 'REPEATABLE READ'
USE_SELECT_FOR_UPDATE = False

# Phase 2: 하이브리드 적용
ADAPTIVE_STRATEGY = True
HIGH_CONTENTION_THRESHOLD = 5

# Phase 3: 완전 최적화
SERIALIZABLE_FOR_CRITICAL = True
REAL_TIME_MONITORING = True
```

### 2. 모니터링 알림

```python
# CloudWatch/Grafana 메트릭
METRICS_TO_MONITOR = [
    'lock_wait_time_avg',
    'deadlock_count_per_minute',
    'transaction_retry_rate',
    'stock_reservation_success_rate',
    'concurrent_reservation_count'
]

# 알림 임계값
ALERT_THRESHOLDS = {
    'lock_wait_time_avg': 100,  # ms
    'deadlock_count_per_minute': 5,
    'transaction_retry_rate': 0.1,  # 10%
    'stock_reservation_success_rate': 0.95  # 95%
}
```
