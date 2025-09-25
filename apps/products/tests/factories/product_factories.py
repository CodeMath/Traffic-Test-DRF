"""
상품 관련 Factory 클래스들
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import factory
from django.contrib.auth.models import User
from django.utils import timezone

from apps.products.models import (
    Product,
    ProductStatus,
    ProductStock,
    StockReservation,
    StockReservationStatus,
    StockTransaction,
    StockTransactionType,
)


class ProductFactory(factory.django.DjangoModelFactory):
    """상품 Factory"""

    class Meta:
        model = Product

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"테스트 상품 {n}")
    description = factory.LazyAttribute(lambda obj: f"{obj.name} 설명")
    status = ProductStatus.ACTIVE
    price = factory.LazyFunction(lambda: Decimal("10000.00"))


class ProductStockFactory(factory.django.DjangoModelFactory):
    """상품 재고 Factory"""

    class Meta:
        model = ProductStock

    id = factory.LazyFunction(uuid.uuid4)
    product = factory.SubFactory(ProductFactory)
    physical_stock = 100
    reserved_stock = 0
    available_stock = 100
    min_stock_level = 10
    reorder_point = 20
    warehouse_code = factory.Sequence(lambda n: f"WH{n:04d}")


class UserFactory(factory.django.DjangoModelFactory):
    """사용자 Factory"""

    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    is_active = True


class StockReservationFactory(factory.django.DjangoModelFactory):
    """재고 예약 Factory"""

    class Meta:
        model = StockReservation

    id = factory.LazyFunction(uuid.uuid4)
    product_stock = factory.SubFactory(ProductStockFactory)
    quantity = 10
    order_id = factory.Sequence(lambda n: f"ORDER-{n:06d}")
    user_id = factory.SubFactory(UserFactory)
    status = StockReservationStatus.PENDING
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=30))

    @factory.post_generation
    def update_stock(self, create, extracted, **kwargs):
        """예약 생성 후 재고 수량 업데이트"""
        if create and self.status == StockReservationStatus.PENDING:
            stock = self.product_stock
            stock.reserved_stock += self.quantity
            stock.available_stock -= self.quantity
            stock.save()


class StockTransactionFactory(factory.django.DjangoModelFactory):
    """재고 트랜잭션 Factory"""

    class Meta:
        model = StockTransaction

    id = factory.LazyFunction(uuid.uuid4)
    product_stock = factory.SubFactory(ProductStockFactory)
    transaction_type = StockTransactionType.INBOUND
    quantity = 50
    reference_type = "inbound"
    reference_id = factory.Sequence(lambda n: f"REF-{n:06d}")
    before_physical = 50
    after_physical = 100
    before_available = 50
    after_available = 100
    notes = factory.LazyAttribute(lambda obj: f"{obj.transaction_type} 트랜잭션")
    metadata = factory.Dict({})


class LowStockProductFactory(ProductStockFactory):
    """재고 부족 상품 Factory"""

    physical_stock = 5
    reserved_stock = 0
    available_stock = 5
    min_stock_level = 10
    reorder_point = 20


class ExpiredReservationFactory(StockReservationFactory):
    """만료된 예약 Factory"""

    status = StockReservationStatus.PENDING
    expires_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=10))


class ConfirmedReservationFactory(StockReservationFactory):
    """확정된 예약 Factory"""

    status = StockReservationStatus.CONFIRMED
    confirmed_at = factory.LazyFunction(timezone.now)


class CancelledReservationFactory(StockReservationFactory):
    """취소된 예약 Factory"""

    status = StockReservationStatus.CANCELLED
    cancelled_at = factory.LazyFunction(timezone.now)
    cancellation_reason = "테스트 취소"


class OutboundTransactionFactory(StockTransactionFactory):
    """출고 트랜잭션 Factory"""

    transaction_type = StockTransactionType.OUTBOUND
    reference_type = "order"
    before_physical = 100
    after_physical = 90
    before_available = 100
    after_available = 90
    quantity = 10


class ReserveTransactionFactory(StockTransactionFactory):
    """예약 트랜잭션 Factory"""

    transaction_type = StockTransactionType.RESERVE
    reference_type = "reservation"
    before_physical = 100
    after_physical = 100
    before_available = 100
    after_available = 90
    quantity = 10


class ReleaseTransactionFactory(StockTransactionFactory):
    """예약 해제 트랜잭션 Factory"""

    transaction_type = StockTransactionType.RELEASE
    reference_type = "reservation"
    before_physical = 100
    after_physical = 100
    before_available = 90
    after_available = 100
    quantity = 10
