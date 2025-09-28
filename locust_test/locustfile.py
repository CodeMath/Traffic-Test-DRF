import json
import random
import time

from locust import FastHttpUser, between, task


class StockTestUser(FastHttpUser):
    """
    대용량 트래픽 테스트를 위한 Locust 사용자 클래스

    테스트 시나리오:
    1. JWT 인증 (10,000개 사용자 계정 중 랜덤 선택)
    2. 상품 목록 조회
    3. 재고 가용성 체크
    4. 재고 예약 (1-100개 랜덤 수량)
    """

    wait_time = between(1, 3)  # 요청 간 1-3초 대기

    # 클래스 변수로 사용자 풀 정의
    USER_POOL_SIZE = 10000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_token: str | None = None
        self.username: str | None = None
        self.current_product_id: str | None = None
        self.available_products: list = []
        self.token_expires_at: float = 0

    def on_start(self):
        """사용자 초기화 및 인증"""
        self.authenticate()

    def authenticate(self):
        """JWT 인증 수행"""
        # 10,000개 사용자 중 랜덤 선택
        user_id = random.randint(0, self.USER_POOL_SIZE - 1)
        self.username = f"user{user_id}"

        auth_data = {
            "username": self.username,
            "password": "password"
        }

        with self.client.post(
            "/api/token/",
            json=auth_data,
            name="01_jwt_auth",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    token_data = response.json()
                    self.access_token = token_data["access"]
                    self.token_expires_at = time.time() + 300  # 5분 후 만료 가정
                    response.success()
                except (KeyError, json.JSONDecodeError) as e:
                    response.failure(f"JWT 토큰 파싱 실패: {e}")
            else:
                response.failure(f"인증 실패: {response.status_code}")

    def get_auth_headers(self):
        """인증 헤더 반환"""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    def check_token_validity(self):
        """토큰 유효성 검사 및 갱신"""
        if time.time() >= self.token_expires_at:
            self.authenticate()

    @task(weight=3)
    def test_product_list(self):
        """상품 목록 조회 테스트"""
        self.check_token_validity()

        with self.client.get(
            "/api/products/",
            headers=self.get_auth_headers(),
            name="02_product_list",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    products = data.get("results", [])

                    if products:
                        # 상품 목록 캐싱 (재고 체크용)
                        self.available_products = products
                        # 랜덤 상품 선택
                        selected_product = random.choice(products)
                        self.current_product_id = selected_product["id"]
                        response.success()
                    else:
                        response.failure("상품 목록이 비어있음")

                except (KeyError, json.JSONDecodeError) as e:
                    response.failure(f"응답 파싱 실패: {e}")
            else:
                response.failure(f"상품 조회 실패: {response.status_code}")

    @task(weight=2)
    def test_stock_availability(self):
        """재고 가용성 체크 테스트"""
        if not self.current_product_id:
            # 상품이 선택되지 않은 경우 상품 목록부터 조회
            self.test_product_list()

        if self.current_product_id:
            self.check_token_validity()

            with self.client.get(
                f"/api/products/stock/available/?product_id={self.current_product_id}",
                headers=self.get_auth_headers(),
                name="03_stock_availability",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        results = data.get("results", [])

                        if results and len(results) > 0:
                            stock_info = results[0]
                            available_stock = stock_info.get("available_stock", 0)

                            if available_stock > 0:
                                response.success()
                            else:
                                response.failure("재고 부족")
                        else:
                            response.failure("재고 정보 없음")

                    except (KeyError, json.JSONDecodeError) as e:
                        response.failure(f"재고 정보 파싱 실패: {e}")
                else:
                    response.failure(f"재고 조회 실패: {response.status_code}")

    @task(weight=1)
    def test_stock_reservation(self):
        """재고 예약 테스트 (1-100개 랜덤 수량)"""
        if not self.current_product_id:
            # 상품이 선택되지 않은 경우 상품 목록부터 조회
            self.test_product_list()

        if self.current_product_id:
            self.check_token_validity()

            # 1-100개 사이 랜덤 수량 생성
            random_quantity = random.randint(1, 100)

            reservation_data = {
                "product_id": self.current_product_id,
                "quantity": random_quantity
            }

            with self.client.post(
                "/api/products/stock/reserve/",
                json=reservation_data,
                headers=self.get_auth_headers(),
                name="04_stock_reserve",
                catch_response=True
            ) as response:
                if response.status_code == 201:
                    try:
                        result = response.json()
                        # 새로운 응답 구조에 맞게 수정
                        if result.get('success', False):
                            response.success()
                        else:
                            # success가 false여도 201이면 비즈니스 로직 상 정상 응답
                            response.success()

                    except json.JSONDecodeError:
                        # JSON 파싱 실패해도 201이면 성공으로 간주
                        response.success()

                elif response.status_code == 400:
                    # 재고 부족 등의 비즈니스 로직 에러는 예상된 응답
                    try:
                        response.json()  # JSON 유효성만 확인
                        response.success()  # 비즈니스 로직 에러도 정상적인 응답으로 처리
                    except json.JSONDecodeError:
                        response.failure("400 응답 파싱 실패")

                else:
                    response.failure(f"재고 예약 실패: {response.status_code}")

    @task(weight=1)
    def test_complete_workflow(self):
        """전체 워크플로우 테스트 (상품 조회 → 재고 체크 → 예약)"""
        # 1. 상품 목록 조회
        self.test_product_list()

        if self.current_product_id:
            # 2. 재고 가용성 체크
            self.test_stock_availability()

            # 3. 재고 예약 시도
            self.test_stock_reservation()


class HighVolumeStockUser(StockTestUser):
    """
    고부하 테스트를 위한 사용자 클래스
    더 짧은 대기시간과 공격적인 요청 패턴
    """
    wait_time = between(0.1, 1.0)  # 더 짧은 대기시간

    @task(weight=5)
    def rapid_stock_check(self):
        """빠른 재고 체크"""
        self.test_stock_availability()

    @task(weight=3)
    def rapid_reservation(self):
        """빠른 예약 시도"""
        self.test_stock_reservation()


# 사용 예시:
# poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000
#
# 고부하 테스트:
# poetry run locust -f locust_test/locustfile.py:HighVolumeStockUser --host=http://localhost:8000
