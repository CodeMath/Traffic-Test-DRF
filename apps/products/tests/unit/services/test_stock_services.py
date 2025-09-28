"""
StockService 단위 테스트
"""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.products.models import StockReservationStatus, StockTransaction, StockTransactionType
from apps.products.services.stock_service import ReservationResult, StockCheckResult, StockService
from apps.products.tests.factories import StockReservationFactory


@pytest.mark.django_db
class TestStockService:
    """StockService 테스트"""

    def test_check_availability_success(self, stock_service, sample_product_stock):
        """재고 가용성 확인 성공 테스트"""
        result = stock_service.check_availablity(product_id=str(sample_product_stock.product.id), quantity=50)

        assert isinstance(result, StockCheckResult)
        assert result.is_available is True
        assert result.available_quantity == 100
        assert result.request_quantity == 50
        assert "완료" in result.message

    def test_check_availability_insufficient_stock(self, stock_service, sample_product_stock):
        """재고 부족 확인 테스트"""
        result = stock_service.check_availablity(product_id=str(sample_product_stock.product.id), quantity=150)

        assert isinstance(result, StockCheckResult)
        assert result.is_available is False
        assert result.available_quantity == 100
        assert result.request_quantity == 150
        assert "부족" in result.message

    def test_check_availability_include_reserved(self, stock_service, sample_product_stock):
        """예약 재고 포함 가용성 확인 테스트"""
        # 예약 재고 설정
        sample_product_stock.reserved_stock = 20
        sample_product_stock.available_stock = 80
        sample_product_stock.save()

        result = stock_service.check_availablity(
            product_id=str(sample_product_stock.product.id), quantity=90, include_reserved=True
        )

        assert result.is_available is True
        assert result.available_quantity == 100  # physical_stock

    def test_check_availability_product_not_found(self, stock_service):
        """존재하지 않는 상품 확인 테스트"""
        result = stock_service.check_availablity(product_id="00000000-0000-0000-0000-000000000000", quantity=10)

        assert result.is_available is False
        assert result.available_quantity == 0
        assert "찾을 수 없습니다" in result.message

    def test_reserve_stock_success(self, stock_service, sample_product_stock, regular_user):
        """재고 예약 성공 테스트"""
        result = stock_service.reserve_stock(
            product_id=str(sample_product_stock.product.id),
            quantity=30,
            user=regular_user,
            order_id="ORDER-123",
            duration_minutes=60,
        )

        assert isinstance(result, ReservationResult)
        assert result.success is True
        assert result.reservation is not None
        assert result.error_message == ""

        # 예약 정보 확인
        reservation = result.reservation
        assert reservation.quantity == 30
        assert reservation.order_id == "ORDER-123"
        assert reservation.status == StockReservationStatus.PENDING
        assert reservation.expires_at > timezone.now()

        # 재고 수량 확인
        sample_product_stock.refresh_from_db()
        assert sample_product_stock.reserved_stock == 30
        assert sample_product_stock.available_stock == 70

    def test_reserve_stock_insufficient_stock(self, stock_service, sample_product_stock, regular_user):
        """재고 부족으로 예약 실패 테스트"""
        result = stock_service.reserve_stock(
            product_id=str(sample_product_stock.product.id), quantity=150, user=regular_user, order_id="ORDER-123"
        )

        assert result.success is False
        assert result.reservation is None
        assert result.error_code == "INSUFFICIENT_STOCK"
        assert "재고 부족" in result.error_message

    def test_reserve_stock_invalid_quantity(self, stock_service, sample_product_stock, regular_user):
        """잘못된 수량으로 예약 실패 테스트"""
        result = stock_service.reserve_stock(
            product_id=str(sample_product_stock.product.id), quantity=0, user=regular_user, order_id="ORDER-123"
        )

        assert result.success is False
        assert result.error_code == "INVALID_QUANTITY"
        assert "0보다" in result.error_message

    def test_reserve_stock_product_not_found(self, stock_service, regular_user):
        """존재하지 않는 상품 예약 실패 테스트"""
        result = stock_service.reserve_stock(
            product_id="00000000-0000-0000-0000-000000000000", quantity=10, user=regular_user, order_id="ORDER-123"
        )

        assert result.success is False
        assert result.error_code == "STOCK_NOT_FOUND"

    def test_confirm_reservation_success(self, stock_service, stock_reservation, superuser):
        """예약 확정 성공 테스트"""
        initial_reserved = stock_reservation.product_stock.reserved_stock

        success, message = stock_service.confirm_reservation(str(stock_reservation.id), superuser)

        assert success is True
        assert "성공" in message

        # 예약 상태 확인
        stock_reservation.refresh_from_db()
        assert stock_reservation.status == StockReservationStatus.CONFIRMED
        assert stock_reservation.confirmed_at is not None

        # 재고 수량 확인 (reserved_stock 감소, available_stock도 추가 감소)
        stock = stock_reservation.product_stock
        stock.refresh_from_db()
        assert stock.reserved_stock == initial_reserved - stock_reservation.quantity

    def test_confirm_reservation_invalid_status(self, stock_service, superuser):
        """잘못된 상태의 예약 확정 실패 테스트"""
        # 이미 확정된 예약 생성
        confirmed_reservation = StockReservationFactory(status=StockReservationStatus.CONFIRMED, confirmed_at=timezone.now())

        success, message = stock_service.confirm_reservation(str(confirmed_reservation.id), superuser)

        assert success is False
        assert "올바르지 않습니다" in message

    def test_confirm_reservation_expired(self, stock_service, expired_reservation, superuser):
        """만료된 예약 확정 실패 테스트"""
        success, message = stock_service.confirm_reservation(str(expired_reservation.id), superuser)

        assert success is False
        assert "만료" in message

    def test_cancel_reservation_success(self, stock_service, stock_reservation, regular_user):
        """예약 취소 성공 테스트 (예약자 본인)"""
        initial_reserved = stock_reservation.product_stock.reserved_stock
        initial_available = stock_reservation.product_stock.available_stock

        success, message = stock_service.cancel_reservation(str(stock_reservation.id), regular_user, reason="고객 요청")

        assert success is True
        assert "성공" in message

        # 예약 상태 확인
        stock_reservation.refresh_from_db()
        assert stock_reservation.status == StockReservationStatus.CANCELLED
        assert stock_reservation.cancelled_at is not None
        assert stock_reservation.cancellation_reason == "고객 요청"

        # 재고 수량 복구 확인
        stock = stock_reservation.product_stock
        stock.refresh_from_db()
        assert stock.reserved_stock == initial_reserved - stock_reservation.quantity
        assert stock.available_stock == initial_available + stock_reservation.quantity

    def test_cancel_reservation_invalid_status(self, stock_service, regular_user):
        """잘못된 상태의 예약 취소 실패 테스트"""
        # 이미 취소된 예약 생성
        cancelled_reservation = StockReservationFactory(status=StockReservationStatus.CANCELLED, cancelled_at=timezone.now())

        success, message = stock_service.cancel_reservation(str(cancelled_reservation.id), regular_user)

        assert success is False
        assert "이미 취소된" in message

    def test_cancel_reservation_force(self, stock_service, superuser):
        """강제 예약 취소 테스트 (슈퍼유저만 가능)"""
        # 확정된 예약 생성
        confirmed_reservation = StockReservationFactory(status=StockReservationStatus.CONFIRMED, confirmed_at=timezone.now())

        success, message = stock_service.cancel_reservation(
            str(confirmed_reservation.id), superuser, reason="강제 취소", force=True
        )

        assert success is True
        assert "성공" in message

        confirmed_reservation.refresh_from_db()
        assert confirmed_reservation.status == StockReservationStatus.CANCELLED

    def test_inbound_stock_success(self, stock_service, sample_product_stock, superuser):
        """재고 입고 성공 테스트"""
        initial_physical = sample_product_stock.physical_stock
        initial_available = sample_product_stock.available_stock

        success, message = stock_service.inbound_stock(
            product_id=str(sample_product_stock.product.id), quantity=50, reason="신규 입고", user=superuser
        )

        assert success is True
        assert "성공" in message

        # 재고 수량 확인
        sample_product_stock.refresh_from_db()
        assert sample_product_stock.physical_stock == initial_physical + 50
        assert sample_product_stock.available_stock == initial_available + 50

        # 트랜잭션 로그 생성 확인
        transaction_log = StockTransaction.objects.filter(
            product_stock=sample_product_stock, transaction_type=StockTransactionType.INBOUND
        ).latest("created_at")

        assert transaction_log.quantity == 50
        assert transaction_log.notes == "신규 입고"

    def test_inbound_stock_product_not_found(self, stock_service, superuser):
        """존재하지 않는 상품 입고 실패 테스트"""
        success, message = stock_service.inbound_stock(
            product_id="00000000-0000-0000-0000-000000000000", quantity=50, user=superuser
        )

        assert success is False
        assert "찾을 수 없습니다" in message

    @patch("apps.products.services.stock_service.cache")
    def test_cache_invalidation(self, mock_cache, stock_service, sample_product_stock):
        """캐시 무효화 테스트"""
        stock_service._invalidate_stock_cache(str(sample_product_stock.product.id))

        # delete_many가 적절한 키들과 함께 호출되었는지 확인
        mock_cache.delete_many.assert_called_once()
        called_keys = mock_cache.delete_many.call_args[0][0]

        expected_keys = [
            f"stock:status:{sample_product_stock.product.id}",
            f"stock:available:{sample_product_stock.product.id}",
            f"stock:detail:{sample_product_stock.product.id}",
        ]

        assert all(key in called_keys for key in expected_keys)

    def test_create_transaction_log(self, stock_service, sample_product_stock):
        """트랜잭션 로그 생성 테스트"""
        metadata = {"reason": "테스트", "operator": "admin"}

        transaction_log = stock_service._create_transaction_log(
            stock=sample_product_stock,
            transaction_type=StockTransactionType.INBOUND,
            quantity=30,
            reference_type="test",
            reference_id="TEST-001",
            metadata=metadata,
        )

        assert transaction_log.product_stock == sample_product_stock
        assert transaction_log.transaction_type == StockTransactionType.INBOUND
        assert transaction_log.quantity == 30
        assert transaction_log.reference_type == "test"
        assert transaction_log.reference_id == "TEST-001"
        assert transaction_log.metadata == metadata
        assert transaction_log.notes == "테스트"

    def test_stock_service_with_concurrent_access(self, stock_service, sample_product_stock, regular_user):
        """동시 접근 테스트 (select_for_update 확인)"""
        # 이 테스트는 실제 데이터베이스 락을 테스트하기 어려우므로
        # 기본적인 동작만 확인
        result = stock_service.reserve_stock(
            product_id=str(sample_product_stock.product.id), quantity=10, user=regular_user, order_id="CONCURRENT-TEST"
        )

        assert result.success is True

    # ================================
    # 권한 관련 테스트 케이스
    # ================================

    def test_confirm_reservation_permission_denied(self, stock_service, stock_reservation, regular_user):
        """예약 확정 권한 없음 테스트 (일반 사용자)"""
        success, message = stock_service.confirm_reservation(str(stock_reservation.id), regular_user)

        assert success is False
        assert "권한이 없습니다" in message

    def test_cancel_reservation_by_superuser(self, stock_service, stock_reservation, superuser):
        """예약 취소 성공 테스트 (슈퍼유저)"""
        success, message = stock_service.cancel_reservation(str(stock_reservation.id), superuser, reason="관리자 취소")

        assert success is True
        assert "성공" in message

    def test_cancel_reservation_permission_denied(self, stock_service, stock_reservation, another_user):
        """예약 취소 권한 없음 테스트 (다른 사용자)"""
        success, message = stock_service.cancel_reservation(str(stock_reservation.id), another_user, reason="타인 취소 시도")

        assert success is False
        assert "권한이 없습니다" in message

    def test_cancel_reservation_force_permission_denied(self, stock_service, regular_user):
        """강제 예약 취소 권한 없음 테스트 (일반 사용자)"""
        # 확정된 예약 생성
        confirmed_reservation = StockReservationFactory(status=StockReservationStatus.CONFIRMED, confirmed_at=timezone.now())

        success, message = stock_service.cancel_reservation(
            str(confirmed_reservation.id), regular_user, reason="강제 취소 시도", force=True
        )

        assert success is False
        assert "강제 취소 권한이 없습니다" in message

    def test_inbound_stock_permission_denied(self, stock_service, sample_product_stock, regular_user):
        """재고 입고 권한 없음 테스트 (일반 사용자)"""
        success, message = stock_service.inbound_stock(
            product_id=str(sample_product_stock.product.id), quantity=50, reason="신규 입고", user=regular_user
        )

        assert success is False
        assert "권한이 없습니다" in message
