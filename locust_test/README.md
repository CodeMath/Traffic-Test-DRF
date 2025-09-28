# Locust 부하 테스트 설정 완료

## 📁 파일 구조

```
locust_test/
├── README.md                 # 이 파일 - 빠른 시작 가이드
├── LOCUST_TUTORIAL.md        # 상세한 튜토리얼 및 가이드
├── locustfile.py             # Locust 테스트 시나리오 구현
└── create_test_users.py      # 10,000명 테스트 사용자 생성 스크립트
```

## 🚀 빠른 시작

### 1. 테스트 사용자 생성

#### 방법 1: Django Management Command (권장)
```bash
# 10,000명의 테스트 사용자 생성
python manage.py create_test_users

# 사용자 수 지정
python manage.py create_test_users --count 5000

# 기존 사용자 삭제 후 새로 생성
python manage.py create_test_users --cleanup
```

#### 방법 2: Django Shell 사용
```bash
# Django shell 실행
python manage.py shell

# shell에서 실행
exec(open('locust_test/create_users_simple.py').read())
```

#### 방법 3: 직접 실행 (환경변수 필요)
```bash
DJANGO_SETTINGS_MODULE=config.settings python locust_test/create_test_users.py
```

### 2. Django 서버 실행
```bash
# Django 개발 서버
python manage.py runserver 0.0.0.0:8000

# Redis 서버 (별도 터미널)
redis-server
```

### 3. Locust 테스트 실행
```bash
# 기본 테스트 (웹 UI)
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000

# 브라우저에서 http://localhost:8089 접속

# 고부하 테스트 클래스 사용
poetry run locust -f locust_test/locustfile.py:HighVolumeStockUser --host=http://localhost:8000
```

## 🎯 구현된 테스트 시나리오

### StockTestUser 클래스
- **사용자**: 10,000명 중 랜덤 선택 (`user0` ~ `user9999`)
- **비밀번호**: 모두 `password`
- **테스트 플로우**:
  1. JWT 인증 (`/api/token/`)
  2. 상품 목록 조회 (`/api/products/`)
  3. 재고 가용성 체크 (`/api/products/stock/available/?product_id=`)
  4. 재고 예약 (`/api/products/stock/reserve/`) - 1-100개 랜덤 수량

### HighVolumeStockUser 클래스
- 더 공격적인 테스트 패턴
- 짧은 대기시간 (0.1-1초)
- 집중적인 재고 체크 및 예약

## 📊 테스트 메트릭

### 모니터링할 주요 지표
- **응답 시간**: 평균/중간값/95백분위수
- **처리량**: 초당 요청 수 (RPS)
- **에러율**: 실패한 요청 비율
- **JWT 인증 성공률**
- **재고 예약 성공률**

### 성능 목표
- 응답 시간: 95%의 요청이 2초 이내
- 에러율: 1% 미만
- 처리량: 분당 1,000건 이상

## 🔧 고급 사용법

### 헤드리스 모드 실행
```bash
# 1,000명 사용자, 10명/초 증가, 5분간 실행
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 10 --run-time 300s --headless

# CSV 결과 저장
poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
  --users 1000 --spawn-rate 10 --run-time 300s --headless \
  --csv=results/load_test
```

### 단계적 부하 증가 테스트
```bash
# 100명 -> 500명 -> 1000명 순차 테스트
for users in 100 500 1000; do
  poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000 \
    --users $users --spawn-rate 25 --run-time 60s --headless \
    --csv=results/test_${users}
done
```

## 📋 상세 문서

더 자세한 내용은 다음 문서들을 참조하세요:

- **[LOCUST_TUTORIAL.md](./LOCUST_TUTORIAL.md)**: 완전한 튜토리얼 및 가이드
- **[Django Silk 프로파일링](http://localhost:8000/silk/)**: 성능 상세 분석
- **[Swagger API 문서](http://localhost:8000/api/schema/swagger-ui/)**: API 엔드포인트 문서

## ⚠️ 주의사항

1. **테스트 환경**: 반드시 개발/테스트 환경에서만 실행
2. **데이터베이스**: 테스트 전 백업 수행
3. **리소스 모니터링**: CPU/메모리 사용량 지속 확인
4. **로그 관리**: 대용량 로그 파일 생성 주의

## 🎉 완료!

이제 대용량 트래픽 부하 테스트를 위한 모든 준비가 완료되었습니다.
체계적인 성능 테스트를 통해 시스템의 한계와 최적화 포인트를 찾아보세요!