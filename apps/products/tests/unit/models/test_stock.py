"""
Stock 관련 모델 단위 테스트
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.products.models import ProductStock, StockReservationStatus, StockTransactionType
from apps.products.tests.factories import (
    ConfirmedReservationFactory,
    ExpiredReservationFactory,
    ProductFactory,
    ProductStockFactory,
    StockReservationFactory,
    StockTransactionFactory,
)


@pytest.mark.django_db
class TestProductStock:
    """ProductStock 모델 테스트"""

    def test_product_stock_creation(self):
        """상품 재고 생성 테스트"""
        stock = ProductStockFactory()

        assert stock.id is not None
        assert stock.product is not None
        assert stock.physical_stock == 100
        assert stock.reserved_stock == 0
        assert stock.available_stock == 100
        assert stock.min_stock_level == 10
        assert stock.reorder_point == 20
        assert stock.warehouse_code.startswith("WH")

    def test_product_stock_str_representation(self):
        """재고 문자열 표현 테스트"""
        product = ProductFactory(name="테스트 상품")
        stock = ProductStockFactory(product=product, available_stock=50)

        expected = "테스트 상품 가용: 50"
        assert str(stock) == expected

    @pytest.mark.django_db(transaction=True)
    def test_stock_constraints(self):
        """재고 제약조건 테스트"""

        # 음수 physical_stock 테스트
        with transaction.atomic():
            with pytest.raises(IntegrityError, match="physical_stock_non_negative"):
                ProductStock.objects.create(product=ProductFactory(), physical_stock=-1, reserved_stock=0, available_stock=0)

        # 음수 reserved_stock 테스트
        with transaction.atomic():
            with pytest.raises(IntegrityError, match="reserved_stock_non_negative"):
                ProductStock.objects.create(product=ProductFactory(), physical_stock=100, reserved_stock=-1, available_stock=100)

    def test_is_low_stock_property(self):
        """재고 부족 프로퍼티 테스트"""
        stock = ProductStockFactory(available_stock=5, min_stock_level=10)
        assert stock.is_low_stock is True

        stock_normal = ProductStockFactory(available_stock=15, min_stock_level=10)
        assert stock_normal.is_low_stock is False

    def test_needs_reorder_property(self):
        """재주문 필요 프로퍼티 테스트"""
        stock = ProductStockFactory(available_stock=15, reorder_point=20)
        assert stock.needs_reorder is True

        stock_normal = ProductStockFactory(available_stock=25, reorder_point=20)
        assert stock_normal.needs_reorder is False

    def test_stock_meta_attributes(self):
        """재고 메타 속성 테스트"""
        stock = ProductStockFactory()

        assert stock._meta.verbose_name == "상품 재고"
        assert stock._meta.verbose_name_plural == "상품 재고"

        # 인덱스 확인
        index_fields = [index.fields for index in stock._meta.indexes]
        assert ["product"] in index_fields
        assert ["available_stock"] in index_fields
        assert ["warehouse_code"] in index_fields

    def test_one_to_one_relationship(self):
        """상품과의 일대일 관계 테스트"""
        product = ProductFactory()
        stock = ProductStockFactory(product=product)

        assert stock.product == product
        assert product.stock_master == stock

        # 같은 상품에 대해 두 번째 재고 생성 시 오류
        with pytest.raises(IntegrityError):
            ProductStockFactory(product=product)


@pytest.mark.django_db
class TestStockReservation:
    """StockReservation 모델 테스트"""

    def test_stock_reservation_creation(self):
        """재고 예약 생성 테스트"""
        reservation = StockReservationFactory()

        assert reservation.id is not None
        assert reservation.product_stock is not None
        assert reservation.quantity == 10
        assert reservation.order_id.startswith("ORDER-")
        assert reservation.status == StockReservationStatus.PENDING
        assert reservation.expires_at > timezone.now()

    def test_reservation_status_choices(self):
        """예약 상태 선택지 테스트"""
        assert StockReservationStatus.PENDING == "pending"
        assert StockReservationStatus.CONFIRMED == "confirmed"
        assert StockReservationStatus.CANCELLED == "cancelled"
        assert StockReservationStatus.EXPIRED == "expired"

    def test_expired_reservation(self):
        """만료된 예약 테스트"""
        reservation = ExpiredReservationFactory()
        assert reservation.expires_at < timezone.now()

    def test_confirmed_reservation(self):
        """확정된 예약 테스트"""
        reservation = ConfirmedReservationFactory()
        assert reservation.status == StockReservationStatus.CONFIRMED
        assert reservation.confirmed_at is not None

    def test_reservation_meta_attributes(self):
        """예약 메타 속성 테스트"""
        reservation = StockReservationFactory()

        assert reservation._meta.verbose_name == "재고 예약"
        assert reservation._meta.verbose_name_plural == "재고 예약"

        # 인덱스 확인
        index_fields = [index.fields for index in reservation._meta.indexes]
        assert ["product_stock", "status"] in index_fields
        assert ["order_id"] in index_fields
        assert ["expires_at", "status"] in index_fields

    def test_reservation_foreign_key_relationship(self):
        """재고와의 외래키 관계 테스트"""
        stock = ProductStockFactory()
        reservation = StockReservationFactory(product_stock=stock)

        assert reservation.product_stock == stock
        assert reservation in stock.reservations.all()


@pytest.mark.django_db
class TestStockTransaction:
    """StockTransaction 모델 테스트"""

    def test_stock_transaction_creation(self):
        """재고 트랜잭션 생성 테스트"""
        transaction = StockTransactionFactory()

        assert transaction.id is not None
        assert transaction.product_stock is not None
        assert transaction.transaction_type == StockTransactionType.INBOUND
        assert transaction.quantity == 50
        assert transaction.reference_type == "inbound"
        assert transaction.reference_id.startswith("REF-")
        assert transaction.before_physical == 50
        assert transaction.after_physical == 100

    def test_transaction_type_choices(self):
        """트랜잭션 타입 선택지 테스트"""
        assert StockTransactionType.INBOUND == "inbound"
        assert StockTransactionType.OUTBOUND == "outbound"
        assert StockTransactionType.RESERVE == "reserve"
        assert StockTransactionType.RELEASE == "release"
        assert StockTransactionType.ADJUST == "adjust"
        assert StockTransactionType.RETURN == "return"
        assert StockTransactionType.TRANSFER == "transfer"

    def test_transaction_with_metadata(self):
        """메타데이터가 있는 트랜잭션 테스트"""
        metadata = {"reason": "테스트 입고", "operator": "admin"}
        transaction = StockTransactionFactory(metadata=metadata)

        assert transaction.metadata == metadata

    def test_transaction_meta_attributes(self):
        """트랜잭션 메타 속성 테스트"""
        transaction = StockTransactionFactory()

        assert transaction._meta.verbose_name == "재고 트랜잭션"
        assert transaction._meta.verbose_name_plural == "재고 트랜잭션"
        assert transaction._meta.ordering == ("-created_at",)

        # 인덱스 확인
        index_fields = [index.fields for index in transaction._meta.indexes]
        assert ["product_stock", "-created_at"] in index_fields
        assert ["transaction_type", "-created_at"] in index_fields
        assert ["reference_type", "reference_id"] in index_fields

    def test_transaction_foreign_key_relationship(self):
        """재고와의 외래키 관계 테스트"""
        stock = ProductStockFactory()
        transaction = StockTransactionFactory(product_stock=stock)

        assert transaction.product_stock == stock
        assert transaction in stock.transactions.all()

    def test_transaction_ordering(self):
        """트랜잭션 정렬 테스트"""
        stock = ProductStockFactory()

        # 시간차를 두고 트랜잭션 생성
        transaction1 = StockTransactionFactory(product_stock=stock)
        transaction2 = StockTransactionFactory(product_stock=stock)

        transactions = stock.transactions.all()
        # created_at 역순으로 정렬되어야 함
        assert transactions.first() == transaction2
        assert transactions.last() == transaction1

    def test_transaction_snapshot_fields(self):
        """트랜잭션 스냅샷 필드 테스트"""
        transaction = StockTransactionFactory(
            before_physical=100, after_physical=110, before_available=90, after_available=100, quantity=10
        )

        # 스냅샷 데이터 검증
        assert transaction.before_physical == 100
        assert transaction.after_physical == 110
        assert transaction.before_available == 90
        assert transaction.after_available == 100
        assert transaction.quantity == 10
