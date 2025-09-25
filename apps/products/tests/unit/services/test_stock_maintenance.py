"""
StockMaintenanceService 단위 테스트
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.products.models import (
    StockReservation,
    StockReservationStatus,
)
from apps.products.services.stock_maintenance import StockMaintenanceService
from apps.products.tests.factories import (
    ConfirmedReservationFactory,
    ExpiredReservationFactory,
    ProductStockFactory,
    StockReservationFactory,
)


@pytest.mark.django_db
class TestStockMaintenanceService:
    """StockMaintenanceService 테스트"""

    def test_clean_expired_reservations_success(self, maintenance_service):
        """만료된 예약 정리 성공 테스트"""
        # 만료된 예약들 생성
        stock = ProductStockFactory()

        expired1 = ExpiredReservationFactory(product_stock=stock)
        expired2 = ExpiredReservationFactory(product_stock=stock)

        # 만료되지 않은 예약도 생성
        active_reservation = StockReservationFactory(product_stock=stock, expires_at=timezone.now() + timedelta(minutes=30))

        # 초기 상태 확인
        expired_count = StockReservation.objects.filter(
            status=StockReservationStatus.PENDING, expires_at__lt=timezone.now()
        ).count()
        assert expired_count == 2

        # 만료된 예약 정리 실행
        cleaned_count = maintenance_service.clean_expired_reservations()

        assert cleaned_count == 2

        # 예약 상태 확인
        expired1.refresh_from_db()
        expired2.refresh_from_db()
        active_reservation.refresh_from_db()

        assert expired1.status == StockReservationStatus.CANCELLED
        assert expired2.status == StockReservationStatus.CANCELLED
        assert active_reservation.status == StockReservationStatus.PENDING

        # 정리 후 만료된 예약이 없는지 확인
        remaining_expired = StockReservation.objects.filter(
            status=StockReservationStatus.PENDING, expires_at__lt=timezone.now()
        ).count()
        assert remaining_expired == 0

    def test_clean_expired_reservations_no_expired(self, maintenance_service):
        """만료된 예약이 없는 경우 테스트"""
        # 활성 예약만 생성
        stock = ProductStockFactory()
        StockReservationFactory(product_stock=stock, expires_at=timezone.now() + timedelta(minutes=30))

        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 0

    def test_clean_expired_reservations_empty_database(self, maintenance_service):
        """예약이 없는 경우 테스트"""
        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 0

    @patch("apps.products.services.stock_maintenance.StockService")
    def test_clean_expired_reservations_partial_failure(self, mock_stock_service_class, maintenance_service):
        """일부 예약 정리 실패 테스트"""
        # StockService 인스턴스의 cancel_reservation 메소드를 모킹
        mock_stock_service = MagicMock()
        mock_stock_service_class.return_value = mock_stock_service

        # 첫 번째 호출은 성공, 두 번째 호출은 실패하도록 설정
        mock_stock_service.cancel_reservation.side_effect = [(True, "성공"), (False, "실패")]

        # 만료된 예약들 생성
        stock = ProductStockFactory()
        ExpiredReservationFactory(product_stock=stock)
        ExpiredReservationFactory(product_stock=stock)

        cleaned_count = maintenance_service.clean_expired_reservations()

        # 성공한 것만 카운트되어야 함
        assert cleaned_count == 1
        assert mock_stock_service.cancel_reservation.call_count == 2

    def test_recalculate_stock_availability_success(self, maintenance_service):
        """재고 가용성 재계산 성공 테스트"""
        # 재고와 예약 생성
        stock = ProductStockFactory(
            physical_stock=100,
            reserved_stock=30,  # 실제와 다른 값 설정
            available_stock=70,
        )

        # 실제 확정된 예약들 생성 (총 20개)
        ConfirmedReservationFactory(product_stock=stock, quantity=10)
        ConfirmedReservationFactory(product_stock=stock, quantity=10)

        # 대기 중인 예약도 생성 (계산에 포함되지 않아야 함)
        StockReservationFactory(product_stock=stock, quantity=5)

        success = maintenance_service.recalculate_stock_availability(str(stock.product.id))

        assert success is True

        # 재고 수량 재계산 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 20  # 확정된 예약만
        assert stock.available_stock == 80  # 100 - 20

    def test_recalculate_stock_availability_no_reservations(self, maintenance_service):
        """예약이 없는 경우 재고 재계산 테스트"""
        stock = ProductStockFactory(
            physical_stock=100,
            reserved_stock=30,  # 잘못된 값
            available_stock=70,
        )

        success = maintenance_service.recalculate_stock_availability(str(stock.product.id))

        assert success is True

        stock.refresh_from_db()
        assert stock.reserved_stock == 0
        assert stock.available_stock == 100

    def test_recalculate_stock_availability_product_not_found(self, maintenance_service):
        """존재하지 않는 상품 재계산 실패 테스트"""
        success = maintenance_service.recalculate_stock_availability("non-existent-id")
        assert success is False

    def test_recalculate_stock_availability_with_mixed_reservations(self, maintenance_service):
        """다양한 상태의 예약이 있는 경우 재계산 테스트"""
        stock = ProductStockFactory(physical_stock=100)

        # 다양한 상태의 예약들 생성
        ConfirmedReservationFactory(product_stock=stock, quantity=15)  # 포함
        StockReservationFactory(product_stock=stock, quantity=10, status=StockReservationStatus.PENDING)  # 제외
        StockReservationFactory(product_stock=stock, quantity=5, status=StockReservationStatus.CANCELLED)  # 제외

        success = maintenance_service.recalculate_stock_availability(str(stock.product.id))

        assert success is True

        stock.refresh_from_db()
        assert stock.reserved_stock == 15  # 확정된 것만
        assert stock.available_stock == 85  # 100 - 15

    @patch("apps.products.services.stock_maintenance.logging.getLogger")
    def test_logging_behavior(self, mock_get_logger, maintenance_service):
        """로깅 동작 테스트"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        # 새로운 서비스 인스턴스를 생성하여 패치가 적용되도록 함
        maintenance_service = StockMaintenanceService()
        # 만료된 예약 정리 로깅
        stock = ProductStockFactory()
        ExpiredReservationFactory(product_stock=stock)

        maintenance_service.clean_expired_reservations()

        # info 로깅이 호출되었는지 확인
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        assert "만료된 예약 정리 완료" in log_message
        assert "1건" in log_message

    @patch("apps.products.services.stock_maintenance.logging.getLogger")
    def test_recalculate_logging(self, mock_get_logger, maintenance_service):
        """재계산 로깅 테스트"""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        # 새로운 서비스 인스턴스를 생성하여 패치가 적용되도록 함
        maintenance_service = StockMaintenanceService()
        stock = ProductStockFactory()

        maintenance_service.recalculate_stock_availability(str(stock.product.id))

        # info 로깅이 호출되었는지 확인
        mock_logger.info.assert_called()
        log_message = mock_logger.info.call_args[0][0]
        assert "재고 가용성 재계산 완료" in log_message

    def test_service_initialization(self):
        """서비스 초기화 테스트"""
        service = StockMaintenanceService()
        assert service.logger is not None
        assert "StockMaintenanceService" in service.logger.name

    def test_integration_clean_and_recalculate(self, maintenance_service):
        """정리와 재계산 통합 테스트"""
        stock = ProductStockFactory(
            physical_stock=100,
            reserved_stock=50,  # 잘못된 값
            available_stock=50,
        )

        # 만료된 예약과 확정된 예약 생성
        ExpiredReservationFactory(product_stock=stock, quantity=10)
        ConfirmedReservationFactory(product_stock=stock, quantity=20)

        # 1. 만료된 예약 정리
        cleaned_count = maintenance_service.clean_expired_reservations()
        assert cleaned_count == 1

        # 2. 재고 재계산
        success = maintenance_service.recalculate_stock_availability(str(stock.product.id))
        assert success is True

        # 최종 상태 확인
        stock.refresh_from_db()
        assert stock.reserved_stock == 20  # 확정된 예약만
        assert stock.available_stock == 80  # 100 - 20

        # 만료된 예약이 취소되었는지 확인
        expired_reservation = StockReservation.objects.filter(product_stock=stock, expires_at__lt=timezone.now()).first()
        if expired_reservation:
            assert expired_reservation.status == StockReservationStatus.CANCELLED
