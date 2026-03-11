from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary='Register a new user',
        request=inline_serializer('RegisterRequest', {
            'username': drf_serializers.CharField(),
            'password': drf_serializers.CharField(),
        }),
        responses={
            201: inline_serializer('RegisterResponse', {
                'access': drf_serializers.CharField(),
                'refresh': drf_serializers.CharField(),
            }),
            400: inline_serializer('RegisterError', {'error': drf_serializers.CharField()}),
        },
    )
    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()
        if not username or not password:
            return Response(
                {'error': 'username and password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(username=username).exists():
            return Response(
                {'error': 'Username already taken'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.create_user(username=username, password=password)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
