from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductStockInboundView, ProductStockListView, ProductStockReserveView, ProductViewSet

router = DefaultRouter()
router.register(r"", ProductViewSet, basename="product")


urlpatterns = [
    path("stock/inbound/", ProductStockInboundView.as_view(), name="product-stock-inbound"),
    path("stock/available/", ProductStockListView.as_view(), name="product-stock-list"),
    # ================================
    # 상품 예약 하기
    # ================================
    path("stock/reserve/", ProductStockReserveView.as_view(), name="product-stock-reserve"),
]


urlpatterns += router.urls
