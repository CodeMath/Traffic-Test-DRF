# Locust 테스트 문제 해결 가이드

## 🔧 일반적인 오류 및 해결 방법

### 1. FastHttpSession 헤더 오류
**오류**: `AttributeError: 'FastHttpSession' object has no attribute 'headers'`

**원인**: Locust의 FastHttpUser에서는 직접 헤더를 설정할 수 없음

**해결**: 각 요청마다 `headers` 파라미터 사용
```python
# 잘못된 방법
self.client.headers.update({"Authorization": f"Bearer {token}"})

# 올바른 방법
headers = {"Authorization": f"Bearer {token}"}
self.client.get("/api/products/", headers=headers)
```

### 2. ReservationResult 시리얼라이저 오류
**오류**: `'ReservationResult' object has no attribute 'product_id'`

**원인**: `ReservationResult` 객체를 시리얼라이저에서 직접 처리하려 함

**해결**: 뷰에서 `ReservationResult`를 응답 데이터로 변환
```python
# 수정된 뷰 구현
reservation_result = serializer.save()
response_data = {
    "success": reservation_result.success,
    "reservation": reservation_result.reservation,
    "error_message": reservation_result.error_message,
    "error_code": reservation_result.error_code,
}
response_serializer = ProductStockReserveResponseSerializer(data=response_data)
```

### 3. Django 설정 문제
**오류**: `Model class django.contrib.contenttypes.models.ContentType doesn't declare an explicit app_label`

**원인**: 필수 Django 앱과 미들웨어 누락

**해결**: `config/base.py`에 다음 추가
```python
BASE_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "silk.middleware.SilkyMiddleware",
]
```

### 4. JWT 인증 실패
**오류**: `401 Unauthorized` 또는 토큰 관련 오류

**해결 순서**:
1. 테스트 사용자 생성 확인
2. Django 서버 실행 확인
3. 인증 테스트 실행
```bash
# 1. 사용자 생성
python manage.py create_test_users

# 2. 서버 실행
python manage.py runserver

# 3. 인증 테스트
python locust_test/test_auth.py
```

### 5. 재고 부족 오류
**오류**: 재고 예약 시 계속 실패

**해결**: 테스트 데이터 생성
```python
# Django shell에서 실행
from apps.products.models import Product, ProductStock

# 테스트 상품 생성
product = Product.objects.create(
    name="테스트 상품",
    description="Locust 테스트용 상품",
    price=10000,
    status="active"
)

# 재고 생성
ProductStock.objects.create(
    product=product,
    physical_stock=10000,
    reserved_stock=0,
    available_stock=10000,
    min_stock_level=100,
    reorder_point=500,
    warehouse_code="WH001"
)
```

## 📊 성능 최적화 팁

### 1. 연결 풀 설정
```python
# locustfile.py에서 연결 최적화
class StockTestUser(FastHttpUser):
    connection_timeout = 60.0
    network_timeout = 60.0
```

### 2. 토큰 캐싱
```python
# 토큰 유효시간 확인으로 불필요한 재인증 방지
def check_token_validity(self):
    if time.time() >= self.token_expires_at:
        self.authenticate()
```

### 3. 에러 처리 최적화
```python
# 예상된 비즈니스 로직 에러는 성공으로 처리
elif response.status_code == 400:
    try:
        response.json()  # JSON 유효성만 확인
        response.success()  # 비즈니스 로직 에러도 정상 응답으로 처리
    except json.JSONDecodeError:
        response.failure("400 응답 파싱 실패")
```

## 🐛 디버깅 도구

### 1. 상세 로깅 활성화
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 2. Django Silk 프로파일링
```bash
# http://localhost:8000/silk/ 접속
# 요청별 상세 성능 분석 가능
```

### 3. 네트워크 모니터링
```bash
# 네트워크 연결 상태 확인
netstat -an | grep 8000

# 포트 사용 확인
lsof -i :8000
```

## 🚀 성능 테스트 권장사항

### 1. 단계적 부하 증가
```bash
# 100명 → 500명 → 1000명 순차 테스트
for users in 100 500 1000; do
  poetry run locust -f locust_test/locustfile.py \
    --users $users --spawn-rate 25 --run-time 60s --headless
done
```

### 2. 리소스 모니터링
- CPU 사용률 <80%
- 메모리 사용률 <80%
- 데이터베이스 연결 수 모니터링

### 3. 성능 목표 설정
- 응답 시간: 95%의 요청이 2초 이내
- 에러율: 1% 미만
- 처리량: 분당 1,000건 이상

이 가이드를 통해 대부분의 Locust 테스트 문제를 해결할 수 있습니다.
