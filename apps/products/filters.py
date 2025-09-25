from django_filters import rest_framework as filters

from apps.products.models import Product, ProductStatus, ProductStock


class ProductFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr="icontains", label="상품명")
    status = filters.ChoiceFilter(choices=ProductStatus.choices, label="상태")
    price = filters.NumberFilter(label="가격")
    price_gte = filters.NumberFilter(field_name="price", lookup_expr="gte", label="가격 이상")
    price_lte = filters.NumberFilter(field_name="price", lookup_expr="lte", label="가격 이하")

    class Meta:
        model = Product
        fields = ["name", "status", "price"]


class ProductStockFilter(filters.FilterSet):
    product_id = filters.UUIDFilter(field_name="product__id", lookup_expr="exact", label="상품 ID")
    available_stock = filters.NumberFilter(label="가용 재고")
    available_stock_gte = filters.NumberFilter(field_name="available_stock", lookup_expr="gte", label="가용 재고 이상")
    available_stock_lte = filters.NumberFilter(field_name="available_stock", lookup_expr="lte", label="가용 재고 이하")

    reserved_stock = filters.NumberFilter(label="예약 재고")
    reserved_stock_gte = filters.NumberFilter(field_name="reserved_stock", lookup_expr="gte", label="예약 재고 이상")
    reserved_stock_lte = filters.NumberFilter(field_name="reserved_stock", lookup_expr="lte", label="예약 재고 이하")

    physical_stock = filters.NumberFilter(label="실제 재고")
    physical_stock_gte = filters.NumberFilter(field_name="physical_stock", lookup_expr="gte", label="실제 재고 이상")
    physical_stock_lte = filters.NumberFilter(field_name="physical_stock", lookup_expr="lte", label="실제 재고 이하")

    class Meta:
        model = ProductStock
        fields = [
            "product_id",
            "available_stock",
            "reserved_stock",
            "physical_stock",
            "warehouse_code",
        ]
