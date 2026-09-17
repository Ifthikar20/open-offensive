from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="csrf"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("me/", views.me, name="me"),
    path("request-access/", views.request_access, name="request-access"),
]
