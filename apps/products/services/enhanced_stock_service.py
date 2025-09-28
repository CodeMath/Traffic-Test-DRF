"""
향상된 재고 관리 서비스 - 하이브리드 격리 수준 전략
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.products.models import (
    Product,
    ProductStock,
    StockReservation,
    StockReservationStatus,
    StockTransaction,
    StockTransactionType,
)


class IsolationLevel(Enum):
    """트랜잭션 격리 수준"""

    READ_COMMITTED = "READ COMMITTED"
    REPEATABLE_READ = "REPEATABLE READ"
    SERIALIZABLE = "SERIALIZABLE"


class ReservationStrategy(Enum):
    """예약 전략"""

    OPTIMISTIC_ONLY = "optimistic_only"
    PESSIMISTIC_ONLY = "pessimistic_only"
    HYBRID = "hybrid"
    ADAPTIVE = "adaptive"


@dataclass
class EnhancedReservationResult:
    """향상된 재고 예약 결과"""

    success: bool
    reservation: StockReservation | None = None
    error_message: str = ""
    error_code: str = ""
    retry_count: int = 0
    conflict_detected: bool = False
    strategy_used: ReservationStrategy | None = None
    isolation_level_used: IsolationLevel | None = None
    execution_time_ms: float = 0.0


class EnhancedStockService:
    """
    향상된 재고 관리 서비스
    - 적응형 격리 수준 전략
    - 하이브리드 락킹 메커니즘
    - 성능 최적화된 충돌 감지
    """

    DEFAULT_RESERVATION_DURATION = 30  # 30분
    MAX_RETRY_COUNT = 3
    BASE_RETRY_DELAY = 0.1  # 100ms

    # 전략 선택 임계값
    HIGH_CONTENTION_THRESHOLD = 5  # 동시 예약 수
    CRITICAL_STOCK_THRESHOLD = 10  # 임계 재고 수량

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.cache = cache

    def reserve_stock_enhanced(
        self,
        product_id: str,
        quantity: int,
        user: User | None = None,
        order_id: str | None = None,
        duration_minutes: int | None = None,
        strategy: ReservationStrategy = ReservationStrategy.ADAPTIVE,
    ) -> EnhancedReservationResult:
        """
        향상된 재고 예약 - 적응형 전략

        Args:
            strategy: ADAPTIVE(기본) - 상황에 따라 최적 전략 선택
                     OPTIMISTIC_ONLY - 낙관적 락킹만 사용
                     PESSIMISTIC_ONLY - 비관적 락킹만 사용
                     HYBRID - 낙관적 + 비관적 조합
        """
        import time

        start_time = time.time()

        if quantity <= 0:
            return EnhancedReservationResult(
                success=False,
                error_message="예약 수량은 0보다 커야 합니다.",
                error_code="INVALID_QUANTITY",
            )

        # 1. 적응형 전략 결정
        if strategy == ReservationStrategy.ADAPTIVE:
            strategy = self._select_optimal_strategy(product_id, quantity)

        # 2. 전략별 실행
        if strategy == ReservationStrategy.OPTIMISTIC_ONLY:
            result = self._reserve_optimistic_only(product_id, quantity, user, order_id, duration_minutes)
        elif strategy == ReservationStrategy.PESSIMISTIC_ONLY:
            result = self._reserve_pessimistic_only(product_id, quantity, user, order_id, duration_minutes)
        elif strategy == ReservationStrategy.HYBRID:
            result = self._reserve_hybrid(product_id, quantity, user, order_id, duration_minutes)
        else:
            result = self._reserve_optimistic_only(product_id, quantity, user, order_id, duration_minutes)

        # 3. 실행 시간 기록
        result.execution_time_ms = (time.time() - start_time) * 1000
        result.strategy_used = strategy

        return result

    def _select_optimal_strategy(self, product_id: str, quantity: int) -> ReservationStrategy:
        """
        상황에 따른 최적 전략 선택
        """
        try:
            # 1. 현재 재고 및 경합 상황 분석
            stock_info = self._analyze_stock_contention(product_id)

            # 2. 높은 경합 상황 + 낮은 재고 → PESSIMISTIC
            if (
                stock_info["concurrent_reservations"] >= self.HIGH_CONTENTION_THRESHOLD
                and stock_info["available_stock"] <= self.CRITICAL_STOCK_THRESHOLD
            ):
                return ReservationStrategy.PESSIMISTIC_ONLY

            # 3. 중간 경합 → HYBRID
            elif stock_info["concurrent_reservations"] >= 2:
                return ReservationStrategy.HYBRID

            # 4. 낮은 경합 → OPTIMISTIC
            else:
                return ReservationStrategy.OPTIMISTIC_ONLY

        except Exception as e:
            self.logger.warning(f"전략 선택 실패, 기본값 사용: {e}")
            return ReservationStrategy.OPTIMISTIC_ONLY

    def _analyze_stock_contention(self, product_id: str) -> dict:
        """재고 경합 상황 분석"""
        cache_key = f"stock_contention:{product_id}"

        # 캐시에서 정보 조회
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return cached_info

        try:
            # DB에서 현재 상황 분석
            stock = ProductStock.objects.select_related("product").get(product__id=product_id)

            # 최근 5분간 동시 예약 시도 수 계산
            recent_reservations = StockReservation.objects.filter(
                product_stock=stock, created_at__gte=timezone.now() - timedelta(minutes=5), status=StockReservationStatus.PENDING
            ).count()

            info = {
                "available_stock": stock.available_stock,
                "concurrent_reservations": recent_reservations,
                "physical_stock": stock.physical_stock,
                "reserved_stock": stock.reserved_stock,
            }

            # 30초간 캐시
            self.cache.set(cache_key, info, 30)
            return info

        except ProductStock.DoesNotExist:
            return {
                "available_stock": 0,
                "concurrent_reservations": 0,
                "physical_stock": 0,
                "reserved_stock": 0,
            }

    def _reserve_optimistic_only(
        self, product_id: str, quantity: int, user: User | None, order_id: str | None, duration_minutes: int | None
    ) -> EnhancedReservationResult:
        """순수 낙관적 락킹 전략"""
        return self._attempt_reservation_with_isolation(
            product_id,
            quantity,
            user,
            order_id,
            duration_minutes,
            isolation_level=IsolationLevel.READ_COMMITTED,
            use_select_for_update=False,
        )

    def _reserve_pessimistic_only(
        self, product_id: str, quantity: int, user: User | None, order_id: str | None, duration_minutes: int | None
    ) -> EnhancedReservationResult:
        """순수 비관적 락킹 전략 (REPEATABLE READ + SELECT FOR UPDATE)"""
        return self._attempt_reservation_with_isolation(
            product_id,
            quantity,
            user,
            order_id,
            duration_minutes,
            isolation_level=IsolationLevel.REPEATABLE_READ,
            use_select_for_update=True,
        )

    def _reserve_hybrid(
        self, product_id: str, quantity: int, user: User | None, order_id: str | None, duration_minutes: int | None
    ) -> EnhancedReservationResult:
        """하이브리드 전략 - 낙관적 시도 후 비관적 폴백"""

        # 1차: 빠른 낙관적 시도
        result = self._attempt_reservation_with_isolation(
            product_id,
            quantity,
            user,
            order_id,
            duration_minutes,
            isolation_level=IsolationLevel.READ_COMMITTED,
            use_select_for_update=False,
            max_retries=1,  # 빠른 실패
        )

        # 2차: 충돌 시 비관적 락킹으로 폴백
        if not result.success and result.conflict_detected:
            self.logger.info(f"낙관적 락킹 실패, 비관적 락킹으로 전환: product={product_id}")
            result = self._attempt_reservation_with_isolation(
                product_id,
                quantity,
                user,
                order_id,
                duration_minutes,
                isolation_level=IsolationLevel.REPEATABLE_READ,
                use_select_for_update=True,
                max_retries=2,
            )

        return result

    def _attempt_reservation_with_isolation(
        self,
        product_id: str,
        quantity: int,
        user: User | None,
        order_id: str | None,
        duration_minutes: int | None,
        isolation_level: IsolationLevel,
        use_select_for_update: bool,
        max_retries: int = 3,
    ) -> EnhancedReservationResult:
        """지정된 격리 수준으로 예약 시도"""

        retry_count = 0

        while retry_count <= max_retries:
            try:
                # 격리 수준 설정
                with self._transaction_with_isolation(isolation_level):
                    # 재고 조회 (락킹 전략에 따라)
                    if use_select_for_update:
                        stock = ProductStock.objects.select_related("product").select_for_update().get(product__id=product_id)
                        current_version = None  # 비관적 락킹에서는 버전 체크 불필요
                    else:
                        stock = ProductStock.objects.select_related("product").get(product__id=product_id)
                        current_version = stock.updated_at

                    # 가용 재고 확인
                    if stock.available_stock < quantity:
                        return EnhancedReservationResult(
                            success=False,
                            error_message=f"재고 부족 (가용: {stock.available_stock}, 요청: {quantity})",
                            error_code="INSUFFICIENT_STOCK",
                            retry_count=retry_count,
                            isolation_level_used=isolation_level,
                        )

                    # 예약 생성
                    duration = duration_minutes or self.DEFAULT_RESERVATION_DURATION
                    expires_at = timezone.now() + timedelta(minutes=duration)

                    reservation = StockReservation.objects.create(
                        product_stock=stock,
                        quantity=quantity,
                        order_id=order_id or "",
                        user_id=user,
                        status=StockReservationStatus.PENDING,
                        expires_at=expires_at,
                    )

                    # 재고 업데이트 (전략에 따라)
                    if use_select_for_update:
                        # 비관적 락킹: 단순 업데이트
                        stock.reserved_stock += quantity
                        stock.available_stock -= quantity
                        stock.save(update_fields=["reserved_stock", "available_stock", "updated_at"])
                        updated_rows = 1
                    else:
                        # 낙관적 락킹: 조건부 업데이트
                        updated_rows = ProductStock.objects.filter(
                            id=stock.id,
                            updated_at=current_version,
                            available_stock__gte=quantity,
                        ).update(
                            reserved_stock=F("reserved_stock") + quantity,
                            available_stock=F("available_stock") - quantity,
                            updated_at=timezone.now(),
                        )

                    # 충돌 검사
                    if updated_rows == 0 and not use_select_for_update:
                        return EnhancedReservationResult(
                            success=False,
                            error_message="동시 업데이트 충돌 감지",
                            error_code="OPTIMISTIC_LOCK_CONFLICT",
                            retry_count=retry_count,
                            conflict_detected=True,
                            isolation_level_used=isolation_level,
                        )

                    # 성공
                    self._create_transaction_log(stock, StockTransactionType.RESERVE, quantity, reservation)
                    self._invalidate_cache(product_id)

                    return EnhancedReservationResult(
                        success=True,
                        reservation=reservation,
                        retry_count=retry_count,
                        isolation_level_used=isolation_level,
                    )

            except IntegrityError as e:
                if "available_stock" in str(e):
                    return EnhancedReservationResult(
                        success=False,
                        error_message="재고 부족 (동시성 제약)",
                        error_code="CONCURRENT_STOCK_EXHAUSTION",
                        retry_count=retry_count,
                        conflict_detected=True,
                        isolation_level_used=isolation_level,
                    )
                raise

            except Exception as e:
                if retry_count < max_retries and self._is_retryable_error(e):
                    retry_count += 1
                    self._backoff_delay(retry_count)
                    continue
                else:
                    return EnhancedReservationResult(
                        success=False,
                        error_message=f"예약 처리 중 오류: {e!s}",
                        error_code="RESERVATION_ERROR",
                        retry_count=retry_count,
                        isolation_level_used=isolation_level,
                    )

        # 최대 재시도 초과
        return EnhancedReservationResult(
            success=False,
            error_message=f"최대 재시도 초과 ({max_retries}회)",
            error_code="MAX_RETRY_EXCEEDED",
            retry_count=retry_count,
            conflict_detected=True,
            isolation_level_used=isolation_level,
        )

    def _transaction_with_isolation(self, isolation_level: IsolationLevel):
        """지정된 격리 수준으로 트랜잭션 실행"""

        class IsolationContext:
            def __init__(self, level: IsolationLevel):
                self.level = level
                self.original_isolation = None

            def __enter__(self):
                # 현재 격리 수준 저장
                with connection.cursor() as cursor:
                    cursor.execute("SHOW transaction_isolation")
                    self.original_isolation = cursor.fetchone()[0]

                    # 새 격리 수준 설정
                    cursor.execute(f"SET TRANSACTION ISOLATION LEVEL {self.level.value}")

                return transaction.atomic().__enter__()

            def __exit__(self, exc_type, exc_val, exc_tb):
                result = transaction.atomic().__exit__(exc_type, exc_val, exc_tb)

                # 원래 격리 수준 복원
                if self.original_isolation:
                    with connection.cursor() as cursor:
                        cursor.execute(f"SET TRANSACTION ISOLATION LEVEL {self.original_isolation}")

                return result

        return IsolationContext(isolation_level)

    def _is_retryable_error(self, error: Exception) -> bool:
        """재시도 가능한 오류인지 판단"""
        error_str = str(error).lower()
        retryable_errors = [
            "deadlock detected",
            "serialization failure",
            "could not serialize access",
            "concurrent update",
        ]
        return any(err in error_str for err in retryable_errors)

    def _backoff_delay(self, retry_count: int):
        """지수 백오프 지연"""
        import random
        import time

        # 지터 추가로 재시도 패턴 분산
        base_delay = self.BASE_RETRY_DELAY * (2**retry_count)
        jitter = random.uniform(0.1, 0.3)
        delay = base_delay + jitter

        time.sleep(delay)

    def _create_transaction_log(
        self, stock: ProductStock, transaction_type: StockTransactionType, quantity: int, reservation: StockReservation
    ):
        """트랜잭션 로그 생성"""
        StockTransaction.objects.create(
            product_stock=stock,
            transaction_type=transaction_type,
            quantity=quantity,
            reference_type="reservation",
            reference_id=str(reservation.id),
            before_physical=stock.physical_stock,
            after_physical=stock.physical_stock,
            before_available=stock.available_stock + quantity,
            after_available=stock.available_stock,
            notes=f"재고 예약: {quantity}개",
        )

    def _invalidate_cache(self, product_id: str):
        """관련 캐시 무효화"""
        cache_keys = [
            f"stock_contention:{product_id}",
            f"stock_info:{product_id}",
            f"product_availability:{product_id}",
        ]
        self.cache.delete_many(cache_keys)
