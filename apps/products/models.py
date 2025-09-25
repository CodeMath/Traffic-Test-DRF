"""
상품 모델 및 재고 모델

"""

import uuid

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

from utils.models.abs import TimeStampedModel


class ProductStatus(models.TextChoices):
    ACTIVE = "active", "판매 중"
    SOLD_OUT = "sold_out", "품절"
    END_OF_SALE = "end_of_sale", "판매 종료"
    INACTIVE = "inactive", "비활성화"


class StockTransactionType(models.TextChoices):
    """재고 트랜잭션 타입"""

    INBOUND = "inbound", "입고"
    OUTBOUND = "outbound", "출고"
    RESERVE = "reserve", "예약"
    RELEASE = "release", "예약 해제"
    ADJUST = "adjust", "조정"
    RETURN = "return", "반품"
    TRANSFER = "transfer", "이동"


class StockReservationStatus(models.TextChoices):
    """재고 예약 상태"""

    PENDING = "pending", "대기중"
    CONFIRMED = "confirmed", "확정"
    CANCELLED = "cancelled", "취소"
    EXPIRED = "expired", "만료"


class Product(TimeStampedModel):
    """
    상품 모델
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name="상품명")
    description = models.TextField(verbose_name="상품설명")
    status = models.CharField(max_length=255, verbose_name="상태", choices=ProductStatus.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="가격", validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "상품"
        verbose_name_plural = "상품"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["-created_at"]),  # 최신순 정렬 최적화
            models.Index(fields=["status"]),  # 상태별 필터링 최적화
            models.Index(fields=["status", "-created_at"]),  # 복합 인덱스
        ]


# ================================
# 상품 재고 모델
# ================================


class ProductStock(TimeStampedModel):
    """
    상품 재고 마스터 테이블
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(Product, on_delete=models.CASCADE, verbose_name="상품", related_name="stock_master")
    physical_stock = models.IntegerField(verbose_name="실제 재고", default=0)
    reserved_stock = models.IntegerField(verbose_name="예약 재고", default=0)
    available_stock = models.IntegerField(verbose_name="가용 재고", default=0)

    # 임계값
    min_stock_level = models.IntegerField(verbose_name="최소 재고 수준", default=0)
    reorder_point = models.IntegerField(verbose_name="재고 주문 포인트", default=0)

    # 메타데이터
    warehouse_code = models.CharField(max_length=255, verbose_name="창고 코드", default="3077006")

    def __str__(self):
        return f"{self.product.name} 가용: {self.available_stock}"

    class Meta:
        verbose_name = "상품 재고"
        verbose_name_plural = "상품 재고"
        indexes = (
            models.Index(fields=["product"]),
            models.Index(fields=["available_stock"]),
            models.Index(fields=["warehouse_code"]),
        )
        constraints = (
            models.CheckConstraint(
                condition=models.Q(physical_stock__gte=0),  # 5.1 버전 이상 사용, 이전 버전은 check 사용해야함
                name="physical_stock_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_stock__gte=0),
                name="reserved_stock_non_negative",
            ),
        )

    @property
    def is_low_stock(self) -> bool:
        """재고 부족 알림"""
        return self.available_stock <= self.min_stock_level

    @property
    def needs_reorder(self) -> bool:
        """재고 주문 필요 알림"""
        return self.available_stock <= self.reorder_point


# ================================
# 재고 예약 모델
# ================================


class StockReservation(TimeStampedModel):
    """
    재고 예약 테이블
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_stock = models.ForeignKey(
        ProductStock, on_delete=models.CASCADE, verbose_name="상품 재고", related_name="reservations"
    )
    quantity = models.IntegerField(verbose_name="예약 수량")

    order_id = models.CharField(max_length=255, verbose_name="주문 ID", db_index=True, default="", blank=True)
    user_id = models.ForeignKey(User, verbose_name="예약자", on_delete=models.CASCADE, related_name="reservations")
    status = models.CharField(max_length=255, verbose_name="예약 상태", choices=StockReservationStatus.choices)
    # 시간 관련
    expires_at = models.DateTimeField(verbose_name="만료 시간")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "재고 예약"
        verbose_name_plural = "재고 예약"
        indexes = (
            models.Index(fields=["product_stock", "status"]),
            models.Index(fields=["user_id", "status"]),
            models.Index(fields=["order_id"]),
            models.Index(fields=["expires_at", "status"]),
        )


# ================================
# 재고 트랜잭션 모델
# ================================


class StockTransaction(TimeStampedModel):
    """
    재고 트랜잭션 테이블
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_stock = models.ForeignKey(
        ProductStock, on_delete=models.CASCADE, verbose_name="상품 재고", related_name="transactions"
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=StockTransactionType.choices,
        verbose_name="트랜잭션 유형",
    )
    quantity = models.IntegerField(verbose_name="수량")

    # 참조 정보
    reference_type = models.CharField(max_length=50, default="", blank=True, verbose_name="참조 타입")
    reference_id = models.CharField(max_length=100, default="", blank=True, verbose_name="참조 ID")

    # 스냅샷
    before_physical = models.IntegerField()
    after_physical = models.IntegerField()
    before_available = models.IntegerField()
    after_available = models.IntegerField()

    # 추가 정보
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "재고 트랜잭션"
        verbose_name_plural = "재고 트랜잭션"
        indexes = (
            models.Index(fields=["product_stock", "-created_at"]),
            models.Index(fields=["transaction_type", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        )
        ordering = ("-created_at",)
