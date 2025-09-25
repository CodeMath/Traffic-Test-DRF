"""
Product 모델 단위 테스트
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.products.models import Product, ProductStatus
from apps.products.tests.factories import ProductFactory


@pytest.mark.django_db
class TestProduct:
    """Product 모델 테스트"""

    def test_product_creation(self):
        """상품 생성 테스트"""
        product = ProductFactory()

        assert product.id is not None
        assert product.name.startswith("테스트 상품")
        assert product.description is not None
        assert product.status == ProductStatus.ACTIVE
        assert product.price == Decimal("10000.00")
        assert product.created_at is not None
        assert product.updated_at is not None

    def test_product_str_representation(self):
        """상품 문자열 표현 테스트"""
        product = ProductFactory(name="테스트 상품")
        assert str(product) == "테스트 상품"

    def test_product_status_choices(self):
        """상품 상태 선택지 테스트"""
        assert ProductStatus.ACTIVE == "active"
        assert ProductStatus.SOLD_OUT == "sold_out"
        assert ProductStatus.END_OF_SALE == "end_of_sale"
        assert ProductStatus.INACTIVE == "inactive"

    def test_product_price_decimal_field(self):
        """상품 가격 소수점 필드 테스트"""
        product = ProductFactory(price=Decimal("12345.67"))
        assert product.price == Decimal("12345.67")

    def test_product_name_max_length(self):
        """상품명 최대 길이 테스트"""
        long_name = "a" * 256
        product = ProductFactory.build(name=long_name)

        with pytest.raises(ValidationError):
            product.full_clean()

    def test_product_with_different_statuses(self):
        """다양한 상태의 상품 테스트"""
        statuses = [ProductStatus.ACTIVE, ProductStatus.SOLD_OUT, ProductStatus.END_OF_SALE, ProductStatus.INACTIVE]

        for status in statuses:
            product = ProductFactory(status=status)
            assert product.status == status

    def test_product_meta_attributes(self):
        """상품 메타 속성 테스트"""
        product = ProductFactory()

        assert product._meta.verbose_name == "상품"
        assert product._meta.verbose_name_plural == "상품"

        # 인덱스 확인
        index_fields = [index.fields for index in product._meta.indexes]
        assert ["name"] in index_fields

    def test_product_price_validation(self):
        """상품 가격 유효성 검사 테스트"""
        # 음수 가격 - MinValueValidator가 작동함
        with pytest.raises(ValidationError):
            product = ProductFactory.build(price=Decimal("-100.00"))
            product.full_clean()

    def test_product_creation_with_custom_data(self):
        """커스텀 데이터로 상품 생성 테스트"""
        product = ProductFactory(
            name="특별한 상품", description="특별한 설명", status=ProductStatus.SOLD_OUT, price=Decimal("25000.50")
        )

        assert product.name == "특별한 상품"
        assert product.description == "특별한 설명"
        assert product.status == ProductStatus.SOLD_OUT
        assert product.price == Decimal("25000.50")

    def test_product_ordering(self):
        """상품 정렬 테스트"""
        product1 = ProductFactory(name="A 상품")
        product2 = ProductFactory(name="B 상품")
        product3 = ProductFactory(name="C 상품")

        products = Product.objects.all().order_by("name")
        assert list(products) == [product1, product2, product3]

    def test_product_filtering_by_status(self):
        """상태별 상품 필터링 테스트"""
        active_product = ProductFactory(status=ProductStatus.ACTIVE)
        inactive_product = ProductFactory(status=ProductStatus.INACTIVE)

        active_products = Product.objects.filter(status=ProductStatus.ACTIVE)
        assert active_product in active_products
        assert inactive_product not in active_products

    def test_product_update(self):
        """상품 업데이트 테스트"""
        product = ProductFactory()
        original_updated_at = product.updated_at

        product.name = "업데이트된 상품명"
        product.save()

        product.refresh_from_db()
        assert product.name == "업데이트된 상품명"
        assert product.updated_at > original_updated_at

    def test_product_deletion(self):
        """상품 삭제 테스트"""
        product = ProductFactory()
        product_id = product.id

        product.delete()

        with pytest.raises(Product.DoesNotExist):
            Product.objects.get(id=product_id)
