from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from invites.models import AccessRequest

from .serializers import RegisterSerializer, UserSerializer


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """GET to receive a CSRF cookie the SPA echoes back as X-CSRFToken."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "ok"})


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """Invite-gated registration: needs a valid, unused invite code."""
    ser = RegisterSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = ser.save()
    login(request, user)
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(
        request,
        username=request.data.get("username"),
        password=request.data.get("password"),
    )
    if user is None:
        return Response({"detail": "Invalid username or password."},
                        status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    return Response(UserSerializer(user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"detail": "ok"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([AllowAny])
def request_access(request):
    """Public waitlist submission from the landing page."""
    email = (request.data.get("email") or "").strip()
    if not email:
        return Response({"detail": "An email is required."}, status=status.HTTP_400_BAD_REQUEST)
    AccessRequest.objects.create(
        email=email,
        name=(request.data.get("name") or "").strip(),
        note=(request.data.get("note") or "").strip(),
    )
    return Response({"detail": "Thanks — you're on the list."}, status=status.HTTP_201_CREATED)
