import uuid

from rest_framework import serializers

from apps.products.models import Product, ProductStock, StockReservation
from apps.products.services.stock_service import stock_service


class ProductSerializer(serializers.ModelSerializer):
    """상품 정보 시리얼라이저"""

    class Meta:
        model = Product
        fields = ("id", "name", "description", "price", "status", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ProductStockSerializer(serializers.ModelSerializer):
    """상품 재고 정보 시리얼라이저"""

    class Meta:
        model = ProductStock
        fields = (
            "id",
            "physical_stock",
            "reserved_stock",
            "available_stock",
            "min_stock_level",
            "reorder_point",
            "warehouse_code",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")


class ProductStockInboundSerializer(serializers.Serializer):
    """상품 재고 입고 시리얼라이저"""

    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField()
    reason = serializers.CharField()
    warehouse_code = serializers.CharField()
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def validate_product_id(self, value):
        try:
            Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("상품을 찾을 수 없습니다.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("재고 수량은 0보다 커야 합니다.")
        return value

    def validate_reason(self, value):
        if value is None:
            raise serializers.ValidationError("입고 이유는 필수입니다.")
        return value

    def create(self, validated_data):
        success, message = stock_service.inbound_stock(
            product_id=validated_data["product_id"],
            quantity=validated_data["quantity"],
            reason=validated_data["reason"],
            user=validated_data["user"],
        )
        if success:
            # DRF가 직렬화할 수 있는 객체 리턴
            return validated_data
        else:
            raise serializers.ValidationError(message)


# ================================
# 상품 예약 시리얼라이저
# ================================


class ProdStockReservationSerializer(serializers.ModelSerializer):
    """상품 예약 정보 시리얼라이저"""

    product = ProductSerializer(
        source="product_stock.product",
        read_only=True,
        help_text="상품 정보",
    )

    class Meta:
        model = StockReservation
        fields = ("id", "product", "quantity", "user_id", "status", "expires_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ProductStockReserveResponseSerializer(serializers.Serializer):
    """상품 예약 응답 시리얼라이저"""

    success = serializers.BooleanField(
        help_text="예약 성공 여부",
    )
    reservation = ProdStockReservationSerializer(
        help_text="예약 정보",
        read_only=True,
    )
    error_message = serializers.CharField(help_text="예약 오류 메시지", required=False, allow_blank=True)
    error_code = serializers.CharField(help_text="예약 오류 코드", required=False, allow_blank=True)


class ProductStockReserveSerializer(serializers.Serializer):
    """상품 예약 시리얼라이저"""

    product_id = serializers.UUIDField(
        help_text="상품 ID",
    )
    quantity = serializers.IntegerField(
        help_text="예약 수량",
    )
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def validate_product_id(self, value):
        try:
            Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("상품을 찾을 수 없습니다.", "PRODUCT_NOT_FOUND")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("예약 수량은 0보다 커야 합니다.", "INVALID_QUANTITY")
        return value

    def create(self, validated_data):
        order_id = str(uuid.uuid4())
        result = stock_service.reserve_stock(
            product_id=validated_data["product_id"],
            quantity=validated_data["quantity"],
            user=validated_data["user"],
            order_id=order_id,
        )
        if result.success:
            return result
        else:
            raise serializers.ValidationError(result.error_message, result.error_code)
