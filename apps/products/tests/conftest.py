"""
테스트 전역 설정 및 픽스처
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
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


@pytest.fixture
def regular_user():
    """일반 사용자 픽스처"""
    return User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")


@pytest.fixture
def superuser():
    """슈퍼유저 픽스처"""
    return User.objects.create_superuser(username="admin", email="admin@example.com", password="adminpass123")


@pytest.fixture
def another_user():
    """다른 사용자 픽스처 (권한 테스트용)"""
    return User.objects.create_user(username="otheruser", email="other@example.com", password="otherpass123")


@pytest.fixture
def sample_product():
    """샘플 상품 픽스처"""
    return Product.objects.create(
        name="테스트 상품", description="테스트용 상품입니다", status=ProductStatus.ACTIVE, price=Decimal("10000.00")
    )


@pytest.fixture
def sample_product_stock(sample_product):
    """샘플 상품 재고 픽스처"""
    return ProductStock.objects.create(
        product=sample_product,
        physical_stock=100,
        reserved_stock=0,
        available_stock=100,
        min_stock_level=10,
        reorder_point=20,
        warehouse_code="TEST001",
    )


@pytest.fixture
def low_stock_product():
    """재고 부족 상품 픽스처"""
    product = Product.objects.create(
        name="재고 부족 상품", description="재고가 부족한 테스트 상품", status=ProductStatus.ACTIVE, price=Decimal("5000.00")
    )
    return ProductStock.objects.create(
        product=product,
        physical_stock=5,
        reserved_stock=0,
        available_stock=5,
        min_stock_level=10,
        reorder_point=20,
        warehouse_code="TEST002",
    )


@pytest.fixture
def stock_reservation(sample_product_stock, regular_user):
    """샘플 재고 예약 픽스처"""
    # 예약 생성 후 재고 수량도 업데이트
    reservation = StockReservation.objects.create(
        product_stock=sample_product_stock,
        quantity=10,
        order_id="ORDER-001",
        user_id=regular_user,
        status=StockReservationStatus.PENDING,
        expires_at=timezone.now() + timedelta(minutes=30),
    )

    # 재고 수량 업데이트 (예약 시 실제로 발생하는 변화를 반영)
    sample_product_stock.reserved_stock += reservation.quantity
    sample_product_stock.available_stock -= reservation.quantity
    sample_product_stock.save()

    return reservation


@pytest.fixture
def expired_reservation(sample_product_stock, regular_user):
    """만료된 재고 예약 픽스처"""
    # 만료된 예약 생성 후 재고 수량도 업데이트
    reservation = StockReservation.objects.create(
        product_stock=sample_product_stock,
        quantity=5,
        order_id="ORDER-EXPIRED",
        user_id=regular_user,
        status=StockReservationStatus.PENDING,
        expires_at=timezone.now() - timedelta(minutes=10),
    )

    # 재고 수량 업데이트 (예약 시 실제로 발생하는 변화를 반영)
    sample_product_stock.reserved_stock += reservation.quantity
    sample_product_stock.available_stock -= reservation.quantity
    sample_product_stock.save()

    return reservation


@pytest.fixture
def stock_transaction(sample_product_stock):
    """샘플 재고 트랜잭션 픽스처"""
    return StockTransaction.objects.create(
        product_stock=sample_product_stock,
        transaction_type=StockTransactionType.INBOUND,
        quantity=50,
        reference_type="inbound",
        reference_id="INBOUND-001",
        before_physical=50,
        after_physical=100,
        before_available=50,
        after_available=100,
        notes="초기 입고",
    )


@pytest.fixture
def multiple_products():
    """여러 상품들 픽스처"""
    products = []
    for i in range(3):
        product = Product.objects.create(
            name=f"상품 {i + 1}",
            description=f"테스트용 상품 {i + 1}",
            status=ProductStatus.ACTIVE,
            price=Decimal(f"{(i + 1) * 1000}.00"),
        )
        stock = ProductStock.objects.create(
            product=product,
            physical_stock=(i + 1) * 10,
            reserved_stock=0,
            available_stock=(i + 1) * 10,
            min_stock_level=5,
            reorder_point=10,
            warehouse_code=f"TEST{i + 1:03d}",
        )
        products.append((product, stock))
    return products


@pytest.fixture
def stock_service():
    """StockService 인스턴스 픽스처"""
    from apps.products.services.stock_service import StockService

    return StockService()


@pytest.fixture
def maintenance_service():
    """StockMaintenanceService 인스턴스 픽스처"""
    from apps.products.services.stock_maintenance import StockMaintenanceService

    return StockMaintenanceService()


class BaseTestCase(TestCase):
    """기본 테스트 케이스 클래스"""

    def setUp(self):
        """테스트 설정"""
        self.test_user_id = "test_user_123"
        self.test_order_id = "ORDER_TEST_001"

    def create_test_product(self, name="테스트 상품", price="10000.00"):
        """테스트용 상품 생성"""
        return Product.objects.create(name=name, description=f"{name} 설명", status=ProductStatus.ACTIVE, price=Decimal(price))

    def create_test_stock(self, product, physical_stock=100):
        """테스트용 재고 생성"""
        return ProductStock.objects.create(
            product=product,
            physical_stock=physical_stock,
            reserved_stock=0,
            available_stock=physical_stock,
            min_stock_level=10,
            reorder_point=20,
            warehouse_code="TEST001",
        )
