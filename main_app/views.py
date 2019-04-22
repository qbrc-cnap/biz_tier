from rest_framework import viewsets

from main_app.models import \
    Organization, \
    ResearchGroup, \
    Payment, \
    CnapUser, \
    Purchase, \
    Product, \
    Order

from main_app.serializers import \
    OrganizationSerializer, \
    ResearchGroupSerializer, \
    PaymentSerializer, \
    CnapUserSerializer, \
    PurchaseSerializer, \
    ProductSerializer, \
    OrderSerializer


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

class ResearchGroupViewSet(viewsets.ModelViewSet):
    queryset = ResearchGroup.objects.all()
    serializer_class = ResearchGroupSerializer

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

class CnapUserViewSet(viewsets.ModelViewSet):
    queryset = CnapUser.objects.all()
    serializer_class = CnapUserSerializer

class PurchaseViewSet(viewsets.ModelViewSet):
    queryset = Purchase.objects.all()
    serializer_class = PurchaseSerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
