"""
재고 관리 서비스
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
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

# ================================
# 재고 예약/확인 DTO 설계
# ================================


@dataclass
class StockCheckResult:
    """재고 확인 결과"""

    is_available: bool
    available_quantity: int
    request_quantity: int
    message: str = ""


@dataclass
class ReservationResult:
    """재고 예약 결과"""

    success: bool
    reservation: StockReservation | None = None
    error_message: str = ""
    error_code: str = ""


# ================================
# 재고 서비스
# ================================


class StockService:
    """
    재고 관리 핵심 서비스
    1. 재고 가용성 체크
    2. 재고 예약 (이벤트 기반 - SAGA 패턴 적용을 위한)
    3. 재고 예약 확정 (실제 출고 처리)
    4. 재고 예약 취소/해제 (예약 해제 처리)
    5. 재고 입고 (입고 처리)
    """

    DEFAULT_RESERVATION_DURATION = 30  # 30분

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cache = cache

    def is_superuser(self, user: User) -> bool:
        """
        예약자 권한 체크
        """
        return True if user.is_superuser else False

    @transaction.atomic
    def check_availablity(
        self,
        product_id: str,
        quantity: int,
        include_reserved: bool = False,
    ) -> StockCheckResult:
        """
        재고 가용성 확인

        Args:
            product_id: 상품 ID
            quantity: 요청 수량
            include_reserved: 예약 재고 포함 여부

        Returns:
            StockCheckResult: 재고 가용성 확인 결과
        """
        try:
            stock = ProductStock.objects.select_related("product").get(product___id=product_id)
            available = stock.available_stock

            if include_reserved:
                available = stock.physical_stock

            is_available = available >= quantity

            return StockCheckResult(
                is_available=is_available,
                available_quantity=available,
                request_quantity=quantity,
                message="재고 가용성 확인 완료" if is_available else "재고 부족",
            )

        except ProductStock.DoesNotExist:
            return StockCheckResult(
                is_available=False,
                available_quantity=0,
                request_quantity=quantity,
                message="상품을 찾을 수 없습니다.",
            )

    def reserve_stock(
        self,
        product_id: str,
        quantity: int,
        user: User | None = None,
        order_id: str | None = None,
        duration_minutes: int | None = None,
    ) -> ReservationResult:
        """
        재고 예약 처리

        Args:
            product_id: 상품 ID
            quantity: 예약 요청 수량
            user: 예약자 (User 모델 참조)
            order_id: 주문 ID
            duration_minutes: 예약 유지 시간

        Returns:
            ReservationResult: 재고 예약 결과
        """
        if quantity <= 0:
            return ReservationResult(
                success=False,
                error_message="예약 수량은 0보다 크야야 합니다.",
                error_code="INVALID_QUANTITY",
            )

        try:
            # 재고 조회 및 잠금
            with transaction.atomic():
                stock = ProductStock.objects.select_related("product").select_for_update().get(product__id=product_id)

                # 가용 재고 확인
                if stock.available_stock < quantity:
                    self.logger.warning(
                        f"재고 부족: product={product_id}, available={stock.available_stock}, requested={quantity}"
                    )
                    return ReservationResult(
                        success=False,
                        error_message=f"재고 부족 (가용: {stock.available_stock}, 요청: {quantity})",
                        error_code="INSUFFICIENT_STOCK",
                    )

                # 예약 만료 시간 계산
                duration = duration_minutes or self.DEFAULT_RESERVATION_DURATION
                expires_at = timezone.now() + timedelta(minutes=duration)

                # 예약 생성
                reservation = StockReservation.objects.create(
                    product_stock=stock,
                    quantity=quantity,
                    order_id=order_id or "",
                    user_id=user,
                    status=StockReservationStatus.PENDING,
                    expires_at=expires_at,
                )

                # 재고 수량 업데이트
                stock.reserved_stock = F("reserved_stock") + quantity
                stock.available_stock = F("available_stock") - quantity
                stock.save(update_fields=["reserved_stock", "available_stock"])

            # 트랜잭션 로그 생성
            self._create_transaction_log(
                stock=stock,
                transaction_type=StockTransactionType.RESERVE,
                quantity=quantity,
                reference_type="reservation",
                reference_id=str(reservation.id),
                metadata={"order_id": order_id or "", "user_id": user.username, "duration_minutes": duration},
            )

            # 캐시 무효화
            self._invalidate_stock_cache(product_id)

            self.logger.info(f"재고 예약 성공: reservation={reservation.id}, product={product_id}, quantity={quantity}")

            return ReservationResult(success=True, reservation=reservation)
        except Product.DoesNotExist:
            return ReservationResult(success=False, error_message="상품 정보를 찾을 수 없습니다", error_code="PRODUCT_NOT_FOUND")
        except ProductStock.DoesNotExist:
            return ReservationResult(
                success=False, error_message="상품 재고 정보를 찾을 수 없습니다", error_code="STOCK_NOT_FOUND"
            )
        except Exception as e:
            self.logger.error(f"재고 예약 실패: {e!s}", exc_info=True)
            return ReservationResult(
                success=False, error_message="재고 예약 처리 중 오류가 발생했습니다", error_code="RESERVATION_ERROR"
            )

    @transaction.atomic
    def confirm_reservation(self, reservation_id: str, user: User) -> tuple[bool, str]:
        """
        예약 확정 (실제 출고 처리)
        - 슈퍼유저만 예약 확정 처리 가능

        Args:
            reservation_id: 예약 ID
            user: 예약자 (User 모델 참조)
        Returns:
            Tuple[bool, str]: 예약 확정 결과
        """
        try:
            if not self.is_superuser(user):
                self.logger.warning(f"예약 확정 권한이 없습니다: user={user.username}")
                return False, "예약 확정 권한이 없습니다"

            reservation = StockReservation.objects.select_for_update().get(id=reservation_id)

            if reservation.status != StockReservationStatus.PENDING:
                self.logger.warning(f"예약 상태가 올바르지 않습니다: reservation={reservation_id}, status={reservation.status}")
                return False, "예약 상태가 올바르지 않습니다"

            if reservation.expires_at < timezone.now():
                self.logger.warning(f"예약 만료: reservation={reservation_id}, expires_at={reservation.expires_at}")
                return False, "예약 만료"

            # 재고 조회 및 잠금
            stock = ProductStock.objects.select_for_update().get(id=reservation.product_stock_id)

            # 예약 확정
            reservation.status = StockReservationStatus.CONFIRMED
            reservation.confirmed_at = timezone.now()
            reservation.save(update_fields=["status", "confirmed_at"])

            # 재고 수량 업데이트 (예약 확정시에는 reserved_stock 감소, available_stock도 감소)
            stock.reserved_stock = F("reserved_stock") - reservation.quantity
            stock.available_stock = F("available_stock") - reservation.quantity
            stock.save(update_fields=["reserved_stock", "available_stock"])

            # 트랜잭션 로그 생성
            self._create_transaction_log(
                stock=stock,
                transaction_type=StockTransactionType.OUTBOUND,  # 출고 처리
                quantity=reservation.quantity,
                reference_type="order",
                reference_id=reservation.order_id,
                metadata={"order_id": reservation.order_id},
            )

            # 캐시 무효화
            self._invalidate_stock_cache(stock.product_id)
            self.logger.info(
                f"예약 확정 성공: reservation={reservation_id}, product={stock.product_id}, quantity={reservation.quantity}"
            )
            return True, "예약 확정 성공"

        except StockReservation.DoesNotExist:
            return False, "예약 정보를 찾을 수 없습니다"
        except ProductStock.DoesNotExist:
            return False, "재고 정보를 찾을 수 없습니다"
        except Exception as e:
            self.logger.error(f"예약 확정 실패: {e!s}", exc_info=True)
            return False, "예약 확정 처리 중 오류가 발생했습니다"

    @transaction.atomic
    def cancel_reservation(
        self, reservation_id: str, user: User, reason: str | None = None, force: bool = False
    ) -> tuple[bool, str]:
        """
        예약 취소 (예약 해제 처리)
        - 슈퍼 유저 or 예약자 본인만 취소 처리 가능
        - 슈퍼 유저인 경우: force 옵션 사용 가능

        Args:
            reservation_id: 예약 ID
            user: 요청자 (User 모델 참조)
            reason: 예약 취소 이유
            force: 강제 취소 여부

        Returns:
            Tuple[bool, str]: 예약 취소 결과
        """
        try:
            reservation = StockReservation.objects.select_for_update().get(id=reservation_id)

            # 이미 취소된 예약인지 먼저 확인
            if reservation.status == StockReservationStatus.CANCELLED:
                self.logger.warning(f"이미 취소된 예약입니다. reservation={reservation_id}, status={reservation.status}")
                return False, "이미 취소된 예약입니다"

            # 강제 취소 권한 검사 (슈퍼유저만 가능)
            if force and not self.is_superuser(user):
                self.logger.warning(f"강제 취소 권한이 없습니다: user={user.username}")
                return False, "강제 취소 권한이 없습니다"

            # 권한 검사: 슈퍼유저 또는 예약자 본인만 취소 가능
            if not (self.is_superuser(user) or reservation.user_id == user):
                self.logger.warning(
                    f"예약 취소 권한이 없습니다: user={user.username}, reservation_owner={reservation.user_id.username}"
                )
                return False, "예약 취소 권한이 없습니다"

            # 강제 취소도 아니면서 예약 상태가 대기중이 아닌 경우
            if not force and reservation.status != StockReservationStatus.PENDING:
                self.logger.warning(
                    f"대기 중인 예약만 해제 가능합니다. reservation={reservation_id}, status={reservation.status}"
                )
                return False, "대기 중인 예약만 해제 가능합니다"

            # 재고 조회 및 잠금
            stock = ProductStock.objects.select_for_update().get(id=reservation.product_stock_id)

            # 예약 취소
            reservation.status = StockReservationStatus.CANCELLED
            reservation.cancelled_at = timezone.now()
            reservation.cancellation_reason = reason or ""
            reservation.save(update_fields=["status", "cancelled_at", "cancellation_reason"])

            # 재고 수량 복구(확정되지 않은 경우)
            if reservation.confirmed_at is None:
                stock.reserved_stock = F("reserved_stock") - reservation.quantity
                stock.available_stock = F("available_stock") + reservation.quantity
                stock.save(update_fields=["reserved_stock", "available_stock"])

            # 트랜잭션 로그 생성
            self._create_transaction_log(
                stock=stock,
                transaction_type=StockTransactionType.RELEASE,  # 예약 해제 처리
                quantity=reservation.quantity,
                reference_type="reservation",
                reference_id=str(reservation.id),
                metadata={"reason": reason or "", "force": force},
            )

            # 캐시 무효화
            self._invalidate_stock_cache(stock.product_id)
            self.logger.info(f"예약 취소 성공: reservation={reservation_id}, product={stock.product_id}, reason={reason or ''}")
            return True, "예약 취소 성공"
        except StockReservation.DoesNotExist:
            return False, "예약 정보를 찾을 수 없습니다"
        except ProductStock.DoesNotExist:
            return False, "재고 정보를 찾을 수 없습니다"
        except Exception as e:
            self.logger.error(f"예약 취소 실패: {e!s}", exc_info=True)
            return False, "예약 취소 처리 중 오류가 발생했습니다"

    @transaction.atomic
    def inbound_stock(
        self,
        product_id: str,
        quantity: int,
        warehouse_code: str | None = None,
        reason: str | None = None,
        user: User | None = None,
    ) -> tuple[bool, str]:
        """
        재고 입고 (입고 처리)
        - 슈퍼 유저만 재고 입고 처리 가능

        Args:
            product_id: 상품 ID
            quantity: 입고 수량
            reason: 입고 이유
            warehouse_code: 창고 코드
            user: 입고자 (User 모델 참조)

        Returns:
            Tuple[bool, str]: 재고 입고 결과
        """
        try:
            # 권한 관리
            if not self.is_superuser(user):
                self.logger.warning(f"재고 입고 권한이 없습니다: user={user.username}")
                return False, "재고 입고 권한이 없습니다"
            product = Product.objects.get(id=product_id)
            stock, new = ProductStock.objects.select_for_update().get_or_create(product=product)

            if new:
                stock.warehouse_code = warehouse_code or "3077006"

            # 재고 입고 처리
            reference_id = f"INBOUND-{stock.id}-{timezone.now().strftime('%Y%m%d%H%M%S')}"

            # 재고 입고
            stock.physical_stock = F("physical_stock") + quantity
            stock.available_stock = F("available_stock") + quantity
            stock.save(update_fields=["physical_stock", "available_stock"])

            # 트랜잭션 로그 생성
            self._create_transaction_log(
                stock=stock,
                transaction_type=StockTransactionType.INBOUND,
                quantity=quantity,
                reference_type="inbound",
                reference_id=reference_id,
                metadata={"reason": reason or "", "user": user.username},
            )

            # 캐시 무효화
            self._invalidate_stock_cache(stock.product_id)
            self.logger.info(f"재고 입고 성공: product={stock.product_id}, quantity={quantity}, reason={reason or ''}")
            return True, "재고 입고 성공"
        except ProductStock.DoesNotExist:
            return False, "재고 정보를 찾을 수 없습니다"
        except Exception as e:
            self.logger.error(f"재고 입고 실패: {e!s}", exc_info=True)
            return False, "재고 입고 처리 중 오류가 발생했습니다"

    def _create_transaction_log(
        self,
        stock: ProductStock,
        transaction_type: StockTransactionType,
        quantity: int,
        reference_type: str,
        reference_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> StockTransaction:
        """
        트랜잭션 로그 생성

        Args:
            stock: 재고 정보
            transaction_type: 트랜잭션 유형
            quantity: 수량
            reference_type: 참조 타입
            reference_id: 참조 ID
            metadata: 메타데이터

        """

        stock.refresh_from_db()

        return StockTransaction.objects.create(
            product_stock=stock,
            transaction_type=transaction_type,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            before_physical=stock.physical_stock - (quantity if transaction_type == StockTransactionType.INBOUND else 0),
            after_physical=stock.physical_stock,
            before_available=stock.available_stock
            - (
                quantity
                if transaction_type
                in [
                    StockTransactionType.INBOUND,  # 입고 처리
                    StockTransactionType.OUTBOUND,  # 출고 처리
                ]
                else 0
            ),
            after_available=stock.available_stock,
            metadata=metadata or {},
            notes=metadata.get("reason", "") if metadata else "",
        )

    def _invalidate_stock_cache(self, product_id: str):
        """
        재고 캐시 무효화
        """
        cache_keys = [
            f"stock:status:{product_id}",
            f"stock:available:{product_id}",
            f"stock:detail:{product_id}",
        ]
        self.cache.delete_many(cache_keys)


stock_service = StockService()
