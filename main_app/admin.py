from django.contrib import admin

from main_app.models import *

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name','unit_cost','cnap_workflow_pk', 'is_quantity_limited', 'quantity')


admin.site.register(Product, ProductAdmin)
