from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from invites.models import Invite

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "is_staff")


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    invite_code = serializers.CharField(max_length=64)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        # The invite gate: registration is only possible with a valid, unused code.
        try:
            invite = Invite.objects.get(code=attrs["invite_code"])
        except Invite.DoesNotExist:
            raise serializers.ValidationError({"invite_code": "Unknown invite code."})
        ok, reason = invite.is_valid_for(attrs.get("email", ""))
        if not ok:
            raise serializers.ValidationError({"invite_code": reason})
        attrs["_invite"] = invite
        return attrs

    def create(self, validated):
        invite = validated.pop("_invite")
        user = User.objects.create_user(
            username=validated["username"],
            email=validated.get("email", ""),
            password=validated["password"],
        )
        invite.redeem(user)
        return user
