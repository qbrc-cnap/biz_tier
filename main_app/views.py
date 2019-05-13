import json

from django.shortcuts import render
from django.http import HttpResponseBadRequest, \
    JsonResponse, \
    HttpResponseForbidden, \
    HttpResponse
from django.views import View
from rest_framework import viewsets
from django.contrib.auth import get_user_model


import main_app.tasks as main_tasks

from main_app.models import \
    Organization, \
    ResearchGroup, \
    Payment, \
    CnapUser, \
    Purchase, \
    Product, \
    Order, \
    PendingUser, \
    PendingPipelineRequest

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


class GLApprovalView(View):

    def get(self, request, *args, **kwargs):
        approval_key = kwargs['approval_key']
        print(approval_key)
        try:
            pending_request = PendingPipelineRequest.objects.get(approval_key = approval_key)
            json_info = json.loads(pending_request.info_json)
            gl_code = json_info['GL_CODE']

            requester_email = json_info['EMAIL']
            pi_email = json_info['PI_EMAIL']
            requester_user = get_user_model().objects.get(email=requester_email)
            pi_user = get_user_model().objects.get(email=pi_email)
            requester_name = '%s %s' % (requester_user.first_name, requester_user.last_name)
            pi_name = '%s %s' % (pi_user.first_name, pi_user.last_name)

            context = {}
            context['gl_code'] = gl_code
            context['requester_name'] = requester_name
            context['requester_email'] = requester_email
            context['pi_name'] = pi_name
            context['pi_email'] = pi_email 
            return render(request, 'main_app/gl_code_approval.html', context)
        except PendingPipelineRequest.DoesNotExist:
            return HttpResponseBadRequest()


    def post(self, request, *args, **kwargs):
        '''
        A finance person has submitted the form, which could be approved or rejected
        '''
        try:
            approval_key = kwargs['approval_key']
            print(approval_key)
            pending_request = PendingPipelineRequest.objects.get(approval_key = approval_key)
            pending_request_pk = pending_request.pk
        except PendingPipelineRequest.DoesNotExist:
            return HttpResponseBadRequest()
        except Exception:
            return HttpResponseBadRequest()

        # the post endpoint was ok.  Did they actually approve the request?
        try:
            approved = request.POST['approved']
            approved = True
        except Exception as ex:
            approved = False

        main_tasks.gl_code_approval.delay(pending_request_pk, approved)
        return HttpResponse('Thanks!  Your response has been recorded.')

