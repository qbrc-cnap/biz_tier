import json

from django.shortcuts import render
from django.http import HttpResponseBadRequest, \
    JsonResponse, \
    HttpResponseForbidden, \
    HttpResponse
from django.views import View
from rest_framework import viewsets

import main_app.tasks as main_tasks

from main_app.models import \
    Organization, \
    ResearchGroup, \
    Payment, \
    CnapUser, \
    Purchase, \
    Product, \
    Order, \
    PendingUser

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


class StaffApprovalView(View):

    def get(self, request, *args, **kwargs):
        if request.user.is_staff:
            pending_user_pk = kwargs['pk']
            try:
                pending_user = PendingUser.objects.get(pk=pending_user_pk)
                json_info = json.loads(pending_user.info_json)
                formatted_json_str = json.dumps(json_info, indent=4)
                return render(request, 'main_app/staff_account_approval.html', {'formatted_json_str': formatted_json_str})
            except PendingUser.DoesNotExist:
                return HttpResponseBadRequest()
        else:
            return HttpResponseForbidden()

    def post(self, request, *args, **kwargs):
        '''
        A staff member has submitted the form, indicating they want to proceed with account creation.
        '''
        if request.user.is_staff:
            pending_user_pk = kwargs['pk']
            try:
                pending_user = PendingUser.objects.get(pk=pending_user_pk)
                main_tasks.staff_approve_pending_user.delay(pending_user_pk) # have to send the primary key since async
                return HttpResponse('Process started.')
            except PendingUser.DoesNotExist:
                return HttpResponseBadRequest()
        else:
            return HttpResponseForbidden()


class PIApprovalView(View):

    def get(self, request, *args, **kwargs):
        '''
        When someone clicks visits the link (which includes the large random approval key hash)
        they will come here.  This indicates approval by the PI.  Get the pending user info from
        the database and start the account creation process
        '''
        approval_key = kwargs['approval_key']
        try:
            p = PendingUser.objects.get(approval_key=approval_key)
            main_tasks.pi_approve_pending_user.delay(p.pk)
            return render(request, 'main_app/pi_approval_confirmation.html', {})
        except PendingUser.DoesNotExist:
            return HttpResponseBadRequest()
