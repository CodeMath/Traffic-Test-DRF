"""
재고 관리 워크플로우 통합 테스트
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from apps.products.models import (
    StockReservation,
    StockReservationStatus,
    StockTransaction,
    StockTransactionType,
)
from apps.products.services.stock_maintenance import StockMaintenanceService
from apps.products.services.stock_service import StockService
from apps.products.tests.factories import ProductFactory, ProductStockFactory


@pytest.mark.django_db
class TestStockWorkflows:
    """재고 관리 워크플로우 통합 테스트"""

    def test_complete_order_workflow(self):
        """완전한 주문 워크플로우 테스트"""
        # 1. 상품과 재고 준비
        product = ProductFactory(name="통합테스트 상품", price=Decimal("15000.00"))
        stock = ProductStockFactory(product=product, physical_stock=100, reserved_stock=0, available_stock=100)

        stock_service = StockService()

        # 2. 재고 가용성 확인
        check_result = stock_service.check_availablity(product_id=str(product.id), quantity=30)
        assert check_result.is_available is True

        # 3. 재고 예약
        reservation_result = stock_service.reserve_stock(
            product_id=str(product.id), quantity=30, order_id="INTEGRATION-ORDER-001", user_id="user-123", duration_minutes=60
        )
        assert reservation_result.success is True
        reservation = reservation_result.reservation

        # 재고 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 30
        assert stock.available_stock == 70

        # 4. 예약 확정 (출고)
        success, _ = stock_service.confirm_reservation(str(reservation.id))
        assert success is True

        # 최종 재고 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 70  # 70으로 유지 (출고로 인한 감소)

        # 예약 상태 확인
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CONFIRMED

        # 트랜잭션 로그 확인
        transactions = StockTransaction.objects.filter(product_stock=stock).order_by("created_at")

        assert transactions.count() >= 2  # RESERVE + OUTBOUND
        reserve_tx = transactions.filter(transaction_type=StockTransactionType.RESERVE).first()
        outbound_tx = transactions.filter(transaction_type=StockTransactionType.OUTBOUND).first()

        assert reserve_tx.quantity == 30
        assert outbound_tx.quantity == 30

    def test_order_cancellation_workflow(self):
        """주문 취소 워크플로우 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()

        # 2. 재고 예약
        reservation_result = stock_service.reserve_stock(product_id=str(product.id), quantity=25, order_id="CANCEL-ORDER-001")
        assert reservation_result.success is True

        # 3. 예약 취소
        success, _ = stock_service.cancel_reservation(str(reservation_result.reservation.id), reason="고객 취소 요청")
        assert success is True

        # 재고 복구 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 100

        # 예약 상태 확인
        reservation = reservation_result.reservation
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CANCELLED
        assert "고객 취소" in reservation.cancellation_reason

    def test_expired_reservation_cleanup_workflow(self):
        """만료된 예약 정리 워크플로우 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()
        maintenance_service = StockMaintenanceService()

        # 2. 예약 생성 (즉시 만료되도록)
        with transaction.atomic():
            reservation_result = stock_service.reserve_stock(
                product_id=str(product.id), quantity=20, order_id="EXPIRED-ORDER-001", duration_minutes=1
            )
            reservation = reservation_result.reservation

            # 만료 시간을 과거로 설정
            reservation.expires_at = timezone.now() - timedelta(minutes=5)
            reservation.save()

        # 재고 상태 확인 (예약 후)
        stock.refresh_from_db()
        assert stock.reserved_stock == 20
        assert stock.available_stock == 80

        # 3. 만료된 예약 정리
        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 1

        # 재고 복구 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 100

        # 예약 상태 확인
        reservation.refresh_from_db()
        assert reservation.status == StockReservationStatus.CANCELLED

    def test_stock_inbound_and_availability_workflow(self):
        """재고 입고 및 가용성 재계산 워크플로우 테스트"""
        # 1. 초기 설정 (낮은 재고)
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=10, available_stock=10, min_stock_level=20, reorder_point=30)

        stock_service = StockService()
        maintenance_service = StockMaintenanceService()

        # 재고 부족 상태 확인
        assert stock.is_low_stock is True
        assert stock.needs_reorder is True

        # 2. 재고 입고
        success, _ = stock_service.inbound_stock(product_id=str(product.id), quantity=50, reason="신규 입고")
        assert success is True

        # 입고 후 상태 확인
        stock.refresh_from_db()
        assert stock.physical_stock == 60
        assert stock.available_stock == 60
        assert stock.is_low_stock is False
        assert stock.needs_reorder is False

        # 3. 일부 예약 생성
        reservation_result = stock_service.reserve_stock(product_id=str(product.id), quantity=15, order_id="INBOUND-TEST-ORDER")
        assert reservation_result.success is True

        # 4. 재고 가용성 재계산
        success = maintenance_service.recalculate_stock_availability(str(product.id))
        assert success is True

        # 최종 상태 확인
        stock.refresh_from_db()
        assert stock.physical_stock == 60
        assert stock.reserved_stock == 15
        assert stock.available_stock == 45

    def test_multiple_concurrent_reservations_workflow(self):
        """다중 동시 예약 워크플로우 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()

        # 2. 여러 예약 생성
        reservations = []
        for i in range(5):
            result = stock_service.reserve_stock(
                product_id=str(product.id), quantity=15, order_id=f"CONCURRENT-ORDER-{i + 1:03d}"
            )
            assert result.success is True
            reservations.append(result.reservation)

        # 재고 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 75  # 15 * 5
        assert stock.available_stock == 25

        # 3. 일부 예약 확정, 일부 취소
        # 첫 번째, 세 번째 예약 확정
        for i in [0, 2]:
            success, _ = stock_service.confirm_reservation(str(reservations[i].id))
            assert success is True

        # 두 번째, 네 번째 예약 취소
        for i in [1, 3]:
            success, _ = stock_service.cancel_reservation(str(reservations[i].id))
            assert success is True

        # 최종 재고 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 15  # 마지막 예약만 남음
        assert stock.available_stock == 55  # 100 - 30(확정) - 15(예약중)

        # 예약 상태별 개수 확인
        confirmed_count = StockReservation.objects.filter(product_stock=stock, status=StockReservationStatus.CONFIRMED).count()
        cancelled_count = StockReservation.objects.filter(product_stock=stock, status=StockReservationStatus.CANCELLED).count()
        pending_count = StockReservation.objects.filter(product_stock=stock, status=StockReservationStatus.PENDING).count()

        assert confirmed_count == 2
        assert cancelled_count == 2
        assert pending_count == 1

    def test_stock_adjustment_workflow(self):
        """재고 조정 워크플로우 테스트"""
        # 1. 초기 설정
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=100, available_stock=100)

        stock_service = StockService()
        maintenance_service = StockMaintenanceService()

        # 2. 예약 생성으로 일부 재고 차지
        reservation_result = stock_service.reserve_stock(product_id=str(product.id), quantity=30, order_id="ADJUSTMENT-ORDER")
        assert reservation_result.success is True

        # 3. 물리적 재고 직접 조정 (예: 도난, 파손 등)
        stock.physical_stock = 80  # 20개 감소
        stock.save()

        # 4. 재고 가용성 재계산
        success = maintenance_service.recalculate_stock_availability(str(product.id))
        assert success is True

        # 재계산 후 상태 확인
        stock.refresh_from_db()
        assert stock.physical_stock == 80
        assert stock.reserved_stock == 30  # 예약은 유지
        assert stock.available_stock == 50  # 80 - 30

        # 5. 예약 확정
        success, _ = stock_service.confirm_reservation(str(reservation_result.reservation.id))
        assert success is True

        # 최종 상태 확인
        stock.refresh_from_db()
        assert stock.physical_stock == 80
        assert stock.reserved_stock == 0
        assert stock.available_stock == 50  # 출고로 인한 추가 감소 없음 (이미 반영됨)

    def test_edge_case_zero_stock_workflow(self):
        """재고 0 상황의 엣지 케이스 워크플로우 테스트"""
        # 1. 초기 설정 (재고 10개)
        product = ProductFactory()
        stock = ProductStockFactory(product=product, physical_stock=10, available_stock=10)

        stock_service = StockService()

        # 2. 전체 재고 예약
        result = stock_service.reserve_stock(product_id=str(product.id), quantity=10, order_id="ZERO-STOCK-ORDER")
        assert result.success is True

        # 재고 상태 확인
        stock.refresh_from_db()
        assert stock.available_stock == 0

        # 3. 추가 예약 시도 (실패해야 함)
        result2 = stock_service.reserve_stock(product_id=str(product.id), quantity=1, order_id="ADDITIONAL-ORDER")
        assert result2.success is False
        assert result2.error_code == "INSUFFICIENT_STOCK"

        # 4. 기존 예약 취소
        success, _ = stock_service.cancel_reservation(str(result.reservation.id))
        assert success is True

        # 5. 재고 복구 후 새 예약 성공
        result3 = stock_service.reserve_stock(product_id=str(product.id), quantity=5, order_id="RECOVERY-ORDER")
        assert result3.success is True

        stock.refresh_from_db()
        assert stock.available_stock == 5
