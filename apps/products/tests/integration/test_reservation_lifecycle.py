"""
재고 예약 생명주기 통합 테스트
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.products.models import StockReservationStatus, StockTransaction, StockTransactionType
from apps.products.services.stock_maintenance import StockMaintenanceService
from apps.products.services.stock_service import StockService
from apps.products.tests.factories import ProductFactory, ProductStockFactory


@pytest.mark.django_db
class TestReservationLifecycle:
    """재고 예약 생명주기 통합 테스트"""

    def test_reservation_full_lifecycle_success(self):
        """예약 전체 생명주기 성공 테스트"""
        # 1. 초기 설정
        product = ProductFactory(name="생명주기 테스트 상품")
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        # 사용자 생성
        regular_user = User.objects.create_user(username="testuser", email="test@example.com")
        superuser = User.objects.create_superuser(username="admin", email="admin@example.com")

        stock_service = StockService()

        # 2. 예약 생성 (Pending)
        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id),
            quantity=25,
            user=regular_user,
            order_id="LIFECYCLE-ORDER-001",
            duration_minutes=60,
        )

        assert reservation_result.success is True
        reservation = reservation_result.reservation

        # 예약 상태 확인
        assert reservation.status == StockReservationStatus.PENDING
        assert reservation.quantity == 25
        assert reservation.order_id == "LIFECYCLE-ORDER-001"
        assert reservation.expires_at > timezone.now()

        # 재고 변경 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 25
        assert stock.available_stock == 75

        # 3. 예약 확정 (Confirmed)
        success, message = stock_service.confirm_reservation(str(reservation.id), superuser)

        assert success is True
        assert "성공" in message

        # 예약 상태 변경 확인
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CONFIRMED
        assert reservation.confirmed_at is not None

        # 재고 최종 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0  # 확정으로 예약에서 제거
        assert stock.available_stock == 75  # 출고로 인한 감소

        # 트랜잭션 로그 확인
        transactions = StockTransaction.objects.filter(product_stock=stock).order_by("created_at")

        reserve_tx = transactions.filter(transaction_type=StockTransactionType.RESERVE).first()
        outbound_tx = transactions.filter(transaction_type=StockTransactionType.OUTBOUND).first()

        assert reserve_tx is not None
        assert reserve_tx.quantity == 25
        assert reserve_tx.reference_id == str(reservation.id)

        assert outbound_tx is not None
        assert outbound_tx.quantity == 25
        assert outbound_tx.reference_id == "LIFECYCLE-ORDER-001"

    def test_reservation_lifecycle_with_cancellation(self):
        """취소가 포함된 예약 생명주기 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=50, available_stock=50)

        # 사용자 생성
        regular_user = User.objects.create_user(username="testuser2", email="test2@example.com")
        superuser = User.objects.create_superuser(username="admin2", email="admin2@example.com")

        stock_service = StockService()

        # 2. 예약 생성
        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id), quantity=20, user=regular_user, order_id="CANCEL-LIFECYCLE-001", duration_minutes=30
        )

        assert reservation_result.success is True
        reservation = reservation_result.reservation

        # 3. 예약 취소 (예약자 본인이 취소)
        success, message = stock_service.cancel_reservation(str(reservation.id), regular_user, reason="고객 변심")

        assert success is True

        # 예약 상태 확인
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CANCELLED
        assert reservation.cancelled_at is not None
        assert reservation.cancellation_reason == "고객 변심"

        # 재고 복구 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 50

        # 취소 후 확정 시도 (실패해야 함)
        success, message = stock_service.confirm_reservation(str(reservation.id), superuser)
        assert success is False
        assert "올바르지 않습니다" in message

    def test_reservation_expiration_lifecycle(self):
        """만료를 통한 예약 생명주기 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=80, available_stock=80)

        # 사용자 생성
        regular_user = User.objects.create_user(username="testuser3", email="test3@example.com")

        stock_service = StockService()
        maintenance_service = StockMaintenanceService()

        # 2. 짧은 만료시간으로 예약 생성
        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id), quantity=15, user=regular_user, order_id="EXPIRY-ORDER-001", duration_minutes=1
        )

        reservation = reservation_result.reservation

        # 수동으로 만료시간을 과거로 설정
        reservation.expires_at = timezone.now() - timedelta(minutes=5)
        reservation.save()

        # 3. 만료된 예약 정리
        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 1

        # 예약 상태 확인
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CANCELLED
        assert "만료" in reservation.cancellation_reason

        # 재고 복구 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 80

    def test_multiple_reservations_lifecycle(self):
        """다중 예약 생명주기 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=200, available_stock=200)

        stock_service = StockService()

        # 2. 여러 예약 생성
        reservations = []
        for i in range(4):
            result = stock_service.reserve_stock(
                product_id=str(product.id), quantity=30, order_id=f"MULTI-ORDER-{i + 1:03d}", user_id=f"user-{i + 1}"
            )
            assert result.success is True
            reservations.append(result.reservation)

        # 중간 재고 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 120  # 30 * 4
        assert stock.available_stock == 80

        # 3. 다양한 시나리오로 예약 처리
        # 첫 번째: 확정
        success, _ = stock_service.confirm_reservation(str(reservations[0].id))
        assert success is True

        # 두 번째: 취소
        success, _ = stock_service.cancel_reservation(str(reservations[1].id), reason="재고 부족")
        assert success is True

        # 세 번째: 만료 처리
        reservations[2].expires_at = timezone.now() - timedelta(minutes=1)
        reservations[2].save()

        maintenance_service = StockMaintenanceService()
        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 1

        # 네 번째: 확정
        success, _ = stock_service.confirm_reservation(str(reservations[3].id))
        assert success is True

        # 4. 최종 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0  # 모든 예약 처리됨
        assert stock.available_stock == 140  # 200 - 60(확정된 2개)

        # 예약 상태별 확인
        for i, reservation in enumerate(reservations):
            reservation.refresh_from_db()
            if i == 0 or i == 3:  # 확정된 예약들
                assert reservation.status == StockReservationStatus.CONFIRMED
            else:  # 취소된 예약들
                assert reservation.status == StockReservationStatus.CANCELLED

    def test_reservation_with_insufficient_stock_lifecycle(self):
        """재고 부족 상황의 예약 생명주기 테스트"""
        # 1. 초기 설정 (낮은 재고)
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=20, available_stock=20)

        stock_service = StockService()

        # 2. 재고보다 많은 양 예약 시도
        result = stock_service.reserve_stock(product_id=str(product.id), quantity=25, order_id="INSUFFICIENT-ORDER")

        assert result.success is False
        assert result.error_code == "INSUFFICIENT_STOCK"
        assert result.reservation is None

        # 재고 변화 없음 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 20

        # 3. 가능한 양으로 예약
        result2 = stock_service.reserve_stock(product_id=str(product.id), quantity=15, order_id="POSSIBLE-ORDER")

        assert result2.success is True

        # 4. 나머지 재고보다 많은 양 추가 예약 시도
        result3 = stock_service.reserve_stock(
            product_id=str(product.id),
            quantity=10,  # 현재 가용재고 5개보다 많음
            order_id="ADDITIONAL-ORDER",
        )

        assert result3.success is False
        assert result3.error_code == "INSUFFICIENT_STOCK"

    def test_reservation_concurrent_operations_lifecycle(self):
        """동시 작업이 있는 예약 생명주기 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()

        # 2. 예약 생성
        reservation_result = stock_service.reserve_stock(product_id=str(product.id), quantity=40, order_id="CONCURRENT-ORDER")

        reservation = reservation_result.reservation

        # 3. 동시에 재고 입고 작업
        success, _ = stock_service.inbound_stock(product_id=str(product.id), quantity=50, reason="긴급 입고")
        assert success is True

        # 4. 예약 확정
        success, _ = stock_service.confirm_reservation(str(reservation.id))
        assert success is True

        # 최종 재고 상태 확인
        stock.refresh_from_db()
        assert stock.physical_stock == 150  # 100 + 50
        assert stock.available_stock == 110  # 150 - 40(확정된 예약)

    @patch("apps.products.services.stock_service.timezone.now")
    def test_reservation_time_sensitive_lifecycle(self, mock_now):
        """시간에 민감한 예약 생명주기 테스트"""
        # 현재 시간 고정
        fixed_time = timezone.now()
        mock_now.return_value = fixed_time

        # 1. 초기 설정
        product = ProductFactory()

        stock_service = StockService()

        # 2. 예약 생성 (30분 만료)
        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id), quantity=20, order_id="TIME-SENSITIVE-ORDER", duration_minutes=30
        )

        reservation = reservation_result.reservation
        expected_expiry = fixed_time + timedelta(minutes=30)
        assert reservation.expires_at == expected_expiry

        # 3. 시간 경과 시뮬레이션 (25분 후)
        mock_now.return_value = fixed_time + timedelta(minutes=25)

        # 아직 만료되지 않음 - 확정 가능
        success, _ = stock_service.confirm_reservation(str(reservation.id))
        assert success is True

        # 4. 시간 경과 시뮬레이션 (35분 후 - 이미 확정되었으므로 무관)
        mock_now.return_value = fixed_time + timedelta(minutes=35)

        # 새로운 예약으로 만료 테스트
        reservation_result2 = stock_service.reserve_stock(
            product_id=str(product.id), quantity=15, order_id="SECOND-ORDER", duration_minutes=10
        )

        # 시간을 다시 앞당겨서 만료된 예약 생성
        mock_now.return_value = fixed_time + timedelta(minutes=50)

        # 만료된 예약 확정 시도 (실패)
        success, message = stock_service.confirm_reservation(str(reservation_result2.reservation.id))
        assert success is False
        assert "만료" in message

    def test_reservation_metadata_lifecycle(self):
        """메타데이터가 포함된 예약 생명주기 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()

        # 2. 메타데이터와 함께 예약 생성
        metadata = {
            "customer_id": "CUST-12345",
            "sales_channel": "mobile_app",
            "promotion_code": "SPRING2024",
            "priority": "high",
        }

        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id),
            quantity=30,
            order_id="METADATA-ORDER",
            user_id="user-999",
            duration_minutes=45,
            metadata=metadata,
        )

        reservation = reservation_result.reservation

        # 메타데이터 저장 확인은 현재 모델에 metadata 필드가 없으므로 스킵
        # (실제 구현에서는 reservation 모델에 metadata 필드 추가 필요)

        # 3. 확정 시 추가 메타데이터
        confirm_metadata = {
            "confirmed_by": "operator-001",
            "confirmation_time": timezone.now().isoformat(),
            "notes": "우선순위 주문",
        }

        success, _ = stock_service.confirm_reservation(str(reservation.id), metadata=confirm_metadata)
        assert success is True

        # 트랜잭션 로그의 메타데이터 확인
        outbound_tx = StockTransaction.objects.filter(
            product_stock=stock, transaction_type=StockTransactionType.OUTBOUND, reference_id="METADATA-ORDER"
        ).first()

        assert outbound_tx is not None
        assert "confirmed_by" in outbound_tx.metadata
        assert outbound_tx.metadata["confirmed_by"] == "operator-001"
