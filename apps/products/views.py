"""
재고 관리 뷰
"""

from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, generics

from apps.products.filters import ProductFilter, ProductStockFilter, ProductStockReserveFilter
from apps.products.models import Product, ProductStock, StockReservation
from apps.products.serializers.serialziers import (
    ProdStockReservationSerializer,
    ProductSerializer,
    ProductStockInboundSerializer,
    ProductStockReserveResponseSerializer,
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

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAdminUser()]
        return super().get_permissions()


# ================================
# 상품 재고 뷰
# ================================


@extend_schema(tags=["상품 재고"], summary="관리자용 상품 재고 입고", responses={200: ProductStockInboundSerializer})
class ProductStockInboundView(generics.CreateAPIView):
    """
    상품 재고 입고 뷰
    """

    queryset = ProductStock.objects.all()
    serializer_class = ProductStockInboundSerializer
    permission_classes = (IsAdminUser,)


@extend_schema(tags=["상품 재고"], summary="상품 재고 조회", responses={200: ProductStockSerializer(many=True)})
class ProductStockListView(generics.ListAPIView):
    """
    상품 재고 조회 뷰
    가용 재고가 0 이상인 상품 재고를 조회합니다.
    """

    queryset = (
        ProductStock.objects.select_related("product")
        .only(
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
        .order_by("-updated_at")
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

    @extend_schema(tags=["상품 예약"], summary="상품 재고 예약", responses={200: ProductStockReserveResponseSerializer})
    def post(self, request, *args, **kwargs):
        """
        상품 재고 예약 뷰
        """
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # ReservationResult 객체 반환
        reservation_result = serializer.save()

        # ReservationResult를 응답용 시리얼라이저로 변환
        response_data = {
            "success": reservation_result.success,
            "reservation": ProdStockReservationSerializer(reservation_result.reservation).data,
            "error_message": reservation_result.error_message,
            "error_code": reservation_result.error_code,
        }
        response_serializer = ProductStockReserveResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["상품 예약"], summary="사용자 별 재고 예약 현황 리스트", responses={200: ProdStockReservationSerializer(many=True)}
)
class ProductStockReserveCheckView(generics.ListAPIView):
    """
    사용자 별 재고 예약 현황 리스트
    """

    queryset = StockReservation.objects.select_related("user_id").order_by("-expires_at")
    serializer_class = ProdStockReservationSerializer
    filterset_class = ProductStockReserveFilter
    ordering = ("-expires_at",)

    def get_queryset(self):
        return super().get_queryset().filter(user_id=self.request.user)
