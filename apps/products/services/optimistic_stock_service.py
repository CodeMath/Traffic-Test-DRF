"""
낙관적 락킹 기반 재고 관리 서비스
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.products.models import (
    Product,
    ProductStock,
    StockReservation,
    StockReservationStatus,
    StockTransaction,
    StockTransactionType,
)


@dataclass
class OptimisticReservationResult:
    """낙관적 락킹 기반 재고 예약 결과"""

    success: bool
    reservation: StockReservation | None = None
    error_message: str = ""
    error_code: str = ""
    retry_count: int = 0
    conflict_detected: bool = False


class OptimisticStockService:
    """
    낙관적 락킹 기반 재고 관리 서비스
    - 높은 동시성 지원
    - 재시도 메커니즘 내장
    - 충돌 감지 및 처리
    """

    DEFAULT_RESERVATION_DURATION = 30  # 30분
    MAX_RETRY_COUNT = 3
    BASE_RETRY_DELAY = 0.1  # 100ms

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cache = cache

    def reserve_stock_optimistic(
        self,
        product_id: str,
        quantity: int,
        user: User | None = None,
        order_id: str | None = None,
        duration_minutes: int | None = None,
        max_retries: int | None = None,
    ) -> OptimisticReservationResult:
        """
        낙관적 락킹 기반 재고 예약

        Args:
            product_id: 상품 ID
            quantity: 예약 요청 수량
            user: 예약자
            order_id: 주문 ID
            duration_minutes: 예약 유지 시간
            max_retries: 최대 재시도 횟수

        Returns:
            OptimisticReservationResult: 예약 결과
        """
        if quantity <= 0:
            return OptimisticReservationResult(
                success=False,
                error_message="예약 수량은 0보다 커야 합니다.",
                error_code="INVALID_QUANTITY",
            )

        max_retries = max_retries or self.MAX_RETRY_COUNT
        retry_count = 0

        while retry_count <= max_retries:
            try:
                result = self._attempt_reservation(
                    product_id=product_id,
                    quantity=quantity,
                    user=user,
                    order_id=order_id,
                    duration_minutes=duration_minutes,
                    retry_count=retry_count,
                )

                if result.success or not result.conflict_detected:
                    return result

                # 충돌 감지 시 재시도
                retry_count += 1
                if retry_count <= max_retries:
                    import time

                    # 지수 백오프 지연
                    delay = self.BASE_RETRY_DELAY * (2**retry_count)
                    time.sleep(delay)
                    self.logger.info(f"재고 충돌 감지, 재시도 중: {retry_count}/{max_retries}, delay={delay}s")

            except Exception as e:
                self.logger.error(f"낙관적 락킹 예약 실패: {e!s}", exc_info=True)
                return OptimisticReservationResult(
                    success=False,
                    error_message="재고 예약 처리 중 오류가 발생했습니다",
                    error_code="RESERVATION_ERROR",
                    retry_count=retry_count,
                )

        # 최대 재시도 초과
        return OptimisticReservationResult(
            success=False,
            error_message=f"재고 충돌로 인한 최대 재시도 초과 ({max_retries}회)",
            error_code="MAX_RETRY_EXCEEDED",
            retry_count=retry_count,
            conflict_detected=True,
        )

    def _attempt_reservation(
        self,
        product_id: str,
        quantity: int,
        user: User | None,
        order_id: str | None,
        duration_minutes: int | None,
        retry_count: int,
    ) -> OptimisticReservationResult:
        """
        단일 예약 시도 (낙관적 락킹)
        """
        try:
            with transaction.atomic():
                # 1. 재고 조회 (락 없이)
                stock = ProductStock.objects.select_related("product").get(product__id=product_id)

                # 2. 현재 버전 저장 (updated_at 필드 사용)
                current_version = stock.updated_at
                current_available = stock.available_stock

                # 3. 가용 재고 확인
                if current_available < quantity:
                    self.logger.warning(f"재고 부족: product={product_id}, available={current_available}, requested={quantity}")
                    return OptimisticReservationResult(
                        success=False,
                        error_message=f"재고 부족 (가용: {current_available}, 요청: {quantity})",
                        error_code="INSUFFICIENT_STOCK",
                        retry_count=retry_count,
                    )

                # 4. 예약 만료 시간 계산
                duration = duration_minutes or self.DEFAULT_RESERVATION_DURATION
                expires_at = timezone.now() + timedelta(minutes=duration)

                # 5. 예약 생성
                reservation = StockReservation.objects.create(
                    product_stock=stock,
                    quantity=quantity,
                    order_id=order_id or "",
                    user_id=user,
                    status=StockReservationStatus.PENDING,
                    expires_at=expires_at,
                )

                # 6. 낙관적 업데이트 (버전 체크 포함)
                updated_rows = ProductStock.objects.filter(
                    id=stock.id,
                    updated_at=current_version,  # 버전 체크
                    available_stock__gte=quantity,  # 재고 재확인
                ).update(
                    reserved_stock=F("reserved_stock") + quantity,
                    available_stock=F("available_stock") - quantity,
                    updated_at=timezone.now(),  # 새 버전
                )

                # 7. 충돌 감지
                if updated_rows == 0:
                    # 트랜잭션이 롤백되므로 예약도 자동 취소됨
                    return OptimisticReservationResult(
                        success=False,
                        error_message="동시 업데이트 충돌 감지",
                        error_code="OPTIMISTIC_LOCK_CONFLICT",
                        retry_count=retry_count,
                        conflict_detected=True,
                    )

                # 8. 성공 시 로깅 및 캐시 무효화
                self._create_transaction_log(
                    stock=stock,
                    transaction_type=StockTransactionType.RESERVE,
                    quantity=quantity,
                    reference_type="reservation",
                    reference_id=str(reservation.id),
                    metadata={
                        "order_id": order_id or "",
                        "user_id": user.username if user else "",
                        "duration_minutes": duration,
                        "retry_count": retry_count,
                        "locking_strategy": "optimistic",
                    },
                )

                self._invalidate_stock_cache(product_id)

                self.logger.info(
                    f"낙관적 락킹 예약 성공: reservation={reservation.id}, "
                    f"product={product_id}, quantity={quantity}, retry={retry_count}"
                )

                return OptimisticReservationResult(
                    success=True,
                    reservation=reservation,
                    retry_count=retry_count,
                )

        except Product.DoesNotExist:
            return OptimisticReservationResult(
                success=False,
                error_message="상품 정보를 찾을 수 없습니다",
                error_code="PRODUCT_NOT_FOUND",
                retry_count=retry_count,
            )
        except ProductStock.DoesNotExist:
            return OptimisticReservationResult(
                success=False,
                error_message="상품 재고 정보를 찾을 수 없습니다",
                error_code="STOCK_NOT_FOUND",
                retry_count=retry_count,
            )

    def _create_transaction_log(
        self,
        stock: ProductStock,
        transaction_type: StockTransactionType,
        quantity: int,
        reference_type: str,
        reference_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> StockTransaction:
        """트랜잭션 로그 생성"""
        # 현재 재고 상태 조회 (업데이트 후)
        stock.refresh_from_db()

        return StockTransaction.objects.create(
            product_stock=stock,
            transaction_type=transaction_type,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            before_physical=stock.physical_stock,
            after_physical=stock.physical_stock,
            before_available=stock.available_stock + quantity,  # 업데이트 전 값
            after_available=stock.available_stock,
            metadata=metadata or {},
            notes=metadata.get("reason", "") if metadata else "",
        )

    def _invalidate_stock_cache(self, product_id: str):
        """재고 캐시 무효화"""
        cache_keys = [
            f"stock:status:{product_id}",  # 상품 상태
            f"stock:available:{product_id}",  # 상품 재고
            f"stock:detail:{product_id}",  # 상품 상세
        ]
        self.cache.delete_many(cache_keys)


# 싱글톤 인스턴스
optimistic_stock_service = OptimisticStockService()
