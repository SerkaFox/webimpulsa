from django.urls import path, include

urlpatterns = [
    path('', include('core.urls')),
    path('', include('crm.urls')),
]
