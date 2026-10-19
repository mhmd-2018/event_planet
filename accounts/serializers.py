from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Profile, User


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["full_name", "bio", "website"]


class UserSerializer(serializers.ModelSerializer):
    """Representation of a user (used for `me/` and token responses)."""

    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "is_active", "date_joined", "profile"]


class RegisterSerializer(serializers.ModelSerializer):
    """Account signup. The role is chosen at registration (default: participant)."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        help_text="At least 8 characters.",
    )
    role = serializers.ChoiceField(
        choices=User.Roles.choices,
        default=User.Roles.PARTICIPANT,
        required=False,
    )
    full_name = serializers.CharField(
        source="profile.full_name",
        required=False,
        allow_blank=True,
        max_length=150,
        write_only=True,
    )

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role", "full_name"]

    def validate(self, attrs):
        # Run Django's full password validators (common passwords, similarity
        # to the username, numeric-only, ...) — not just the min-length rule.
        password = attrs.get("password")
        if password:
            candidate = User(
                username=attrs.get("username", ""),
                email=attrs.get("email") or "",
            )
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        role = validated_data.pop("role", User.Roles.PARTICIPANT)
        password = validated_data.pop("password")

        user = User(**validated_data, role=role)
        user.set_password(password)
        user.save()  # signal creates the Profile row

        if profile_data:
            for field, value in profile_data.items():
                setattr(user.profile, field, value)
            user.profile.save()
        return user
