"""
재고 유지보수 서비스
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.products.models import ProductStock, StockReservation, StockReservationStatus, StockTransaction, StockTransactionType
from apps.products.services.stock_service import StockService

# ================================
# 재고 유지보수 서비스
# ================================


class StockMaintenanceService:
    """
    재고 유지보수 서비스
    1. 만료된 예약 정리
    2. 재고 가용성 재계산
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @transaction.atomic
    def clean_expired_reservations(self) -> int:
        """
        만료된 예약 정리
        """
        expired_reservations = StockReservation.objects.filter(
            status=StockReservationStatus.PENDING, expires_at__lt=timezone.now()
        ).select_for_update()

        count = 0
        stock_service = StockService()

        for reservation in expired_reservations:
            success, _ = stock_service.cancel_reservation(reservation.id, reason="예약 시간 만료", force=True)
            if success:
                count += 1

        self.logger.info(f"만료된 예약 정리 완료: {count}건")
        return count

    @transaction.atomic
    def recalculate_stock_availability(self, product_id: str) -> bool:
        """
        재고 가용성 재계산
        """
        try:
            stock = ProductStock.objects.select_for_update().get(product_id=product_id)

            # 실제 예약된 수량 체크
            reserved_stock_total = (
                StockReservation.objects.filter(product_stock=stock, status=StockReservationStatus.CONFIRMED).aggregate(
                    total_quantity=Sum("quantity")
                )["total_quantity"]
                or 0
            )

            # 실제 예약된 수량 업데이트
            stock.reserved_stock = reserved_stock_total
            stock.available_stock = stock.physical_stock - stock.reserved_stock
            stock.save(update_fields=["reserved_stock", "available_stock"])

            self.logger.info(
                f"재고 가용성 재계산 완료: product={product_id}, reserved_stock={stock.reserved_stock}, available_stock={stock.available_stock}"
            )
            return True
        except ProductStock.DoesNotExist:
            self.logger.error(f"재고 정보를 찾을 수 없습니다: product={product_id}")
            return False
        except Exception as e:
            self.logger.error(f"재고 가용성 재계산 실패: {e!s}", exc_info=True)
            return False
