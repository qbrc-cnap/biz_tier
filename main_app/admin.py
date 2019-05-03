from django.contrib import admin

from main_app.models import *

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name','unit_cost','cnap_workflow_pk', 'is_quantity_limited', 'quantity')

class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_type','number','payment_date','client','code', 'payment_amount')

admin.site.register(Product, ProductAdmin)
admin.site.register(Payment, PaymentAdmin)
