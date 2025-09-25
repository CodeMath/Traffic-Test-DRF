"""
재고 관리 뷰
"""

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, generics

from apps.products.filters import ProductFilter, ProductStockFilter
from apps.products.models import Product, ProductStock, StockReservation
from apps.products.serializers.serialziers import (
    ProductSerializer,
    ProductStockInboundSerializer,
    ProductStockReserveSerializer,
    ProductStockSerializer,
)

# ================================
# 프로덕트 API
# ================================


class ProductViewSet(ModelViewSet):
    """
    상품 등록, 조회, 수정, 삭제 뷰셋
    """

    queryset = Product.objects.select_related("stock_master").order_by("-created_at")
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    ordering = ("-created_at",)


# ================================
# 상품 재고 뷰
# ================================


class ProductStockInboundView(generics.CreateAPIView):
    """
    상품 재고 입고 뷰
    """

    queryset = ProductStock.objects.all()
    serializer_class = ProductStockInboundSerializer
    permission_classes = (IsAdminUser,)


class ProductStockListView(generics.ListAPIView):
    """
    상품 재고 조회 뷰
    가용 재고가 0 이상인 상품 재고를 조회합니다.
    """

    queryset = ProductStock.objects.select_related("product").only(
        "id",
        "physical_stock",
        "reserved_stock",
        "available_stock",
        "min_stock_level",
        "reorder_point",
        "warehouse_code",
        "updated_at",
        "product__id",
        "product__name",
        "product__status",
        "product__price",
    )
    serializer_class = ProductStockSerializer
    filterset_class = ProductStockFilter
    ordering = ("-updated_at",)


# ================================
# 상품 예약 하기
# ================================


class ProductStockReserveView(APIView):
    """
    상품 재고 예약 뷰
    """

    serializer_class = ProductStockReserveSerializer

    def post(self, request, *args, **kwargs):
        """
        상품 재고 예약 뷰
        """
        # try:

        # except Exception as e:
        #     return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
