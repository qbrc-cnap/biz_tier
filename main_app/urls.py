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
    path('accounts/staff-approve/<int:pk>', views.StaffApprovalView.as_view(), name='staff_account_approval'),
    path('accounts/approve/<str:approval_key>', views.PIApprovalView.as_view(), name='pi_account_approval'),
    path('api', include(router.urls)),
]
