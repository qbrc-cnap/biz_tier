from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter

from main_app import views

router = DefaultRouter()
router.register(r'organizations', views.OrganizationViewSet)
router.register(r'groups', views.ResearchGroupViewSet)
router.register(r'payments', views.PaymentViewSet)
router.register(r'cnap-users', views.CnapUserViewSet)
router.register(r'purchases', views.PurchaseViewSet)
router.register(r'products', views.ProductViewSet)
router.register(r'orders', views.OrderViewSet)

urlpatterns = [
    path('', include(router.urls))
]
